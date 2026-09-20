import json

import aio_pika

from api.utils.logger import logger
from api.utils.settings import settings

_connection: aio_pika.abc.AbstractRobustConnection | None = None


async def connect() -> aio_pika.abc.AbstractRobustConnection:
    """Establish (or reuse) the robust broker connection.

    Raises on first failure; once established, aio-pika reconnects
    automatically if the broker drops.
    """
    global _connection
    if _connection is None or _connection.is_closed:
        _connection = await aio_pika.connect_robust(settings.RABBITMQ_URL)
    return _connection


async def close() -> None:
    global _connection
    if _connection is not None and not _connection.is_closed:
        await _connection.close()
    _connection = None


async def _publish(queue_name: str, payload: dict) -> None:
    """Publish one persistent message onto a durable queue."""
    connection = await connect()
    channel = await connection.channel()
    try:
        await channel.declare_queue(queue_name, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(payload).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=queue_name,
        )
    finally:
        await channel.close()


async def publish_webhook_event(payload: dict) -> None:
    """Queue a verified Paystack webhook for the worker (BE-10).

    The HTTP handler verifies the signature and answers 200; anything slow
    (poster regeneration, notifications) happens off this queue, never inline.
    """
    logger.debug("Queueing webhook event on %s", settings.WEBHOOK_QUEUE_NAME)
    await _publish(settings.WEBHOOK_QUEUE_NAME, payload)
