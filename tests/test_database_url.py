"""Database URLs retain asyncpg's exact TLS verification policy."""

from urllib.parse import parse_qsl, urlsplit

import pytest

from api.db.url import ASYNCPG_SSL_MODES, build_async_url


@pytest.mark.parametrize("ssl_mode", sorted(ASYNCPG_SSL_MODES))
def test_build_async_url_preserves_every_supported_ssl_mode(ssl_mode):
    url, resolved_ssl_mode = build_async_url(
        f"postgresql://app:secret@db.example.test/balotly?sslmode={ssl_mode}"
    )

    assert resolved_ssl_mode == ssl_mode
    assert url == "postgresql+asyncpg://app:secret@db.example.test/balotly"


def test_build_async_url_strips_asyncpg_incompatible_options_only():
    url, ssl_mode = build_async_url(
        "postgres://app:secret@db.example.test/balotly"
        "?application_name=balotly%20worker"
        "&channel_binding=require"
        "&sslmode=verify-full"
        "&server_settings=x"
        "&server_settings=y"
        "&blank="
    )

    parsed = urlsplit(url)
    assert parsed.scheme == "postgresql+asyncpg"
    assert parse_qsl(parsed.query, keep_blank_values=True) == [
        ("application_name", "balotly worker"),
        ("server_settings", "x"),
        ("server_settings", "y"),
        ("blank", ""),
    ]
    assert ssl_mode == "verify-full"


def test_build_async_url_leaves_existing_asyncpg_url_and_no_ssl_unset():
    url, ssl_mode = build_async_url(
        "postgresql+asyncpg://app:secret@db.example.test/balotly?timeout=30"
    )

    assert url == (
        "postgresql+asyncpg://app:secret@db.example.test/balotly?timeout=30"
    )
    assert ssl_mode is None


@pytest.mark.parametrize(
    "url, message",
    [
        (
            "postgresql://app@db/balotly?sslmode=verify-peer",
            "Unsupported PostgreSQL sslmode",
        ),
        (
            "postgresql://app@db/balotly?sslmode=require&sslmode=verify-full",
            "at most one sslmode",
        ),
        ("sqlite:///tmp/balotly.db", "must use postgres"),
        ("", "non-empty string"),
    ],
)

def test_build_async_url_rejects_ambiguous_or_unsupported_configuration(url, message):
    with pytest.raises(ValueError, match=message):
        build_async_url(url)
