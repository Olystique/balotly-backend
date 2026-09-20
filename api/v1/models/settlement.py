"""Held funds for one candidate over one period, and what happened to them.

Release is an explicit organizer or admin action, never automatic on contest
close (BE-15). A disqualified candidate's settlement is reversed rather than
released, and that is checked at release time.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate
    from api.v1.models.user import User


class SettlementStatus:
    # Funds sit with Paystack under settlement_schedule: manual.
    HELD = "held"
    RELEASED = "released"
    # Withheld from a disqualified candidate.
    REVERSED = "reversed"

    ALL = (HELD, RELEASED, REVERSED)


class Settlement(BaseTableModel):
    __tablename__ = "settlements"

    __table_args__ = (
        CheckConstraint(
            "status IN ('held', 'released', 'reversed')",
            name="ck_settlements_status",
        ),
        CheckConstraint("amount_kobo >= 0", name="ck_settlements_amount_non_negative"),
        CheckConstraint(
            "period_end >= period_start", name="ck_settlements_period"
        ),
        # Every settlement action is logged with when it happened. Who is
        # nullable only because the acting account may later be deleted.
        CheckConstraint(
            "status = 'held' OR actioned_at IS NOT NULL",
            name="ck_settlements_action_is_timestamped",
        ),
        Index("ix_settlements_candidate_status", "candidate_id", "status"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    period_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    period_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    # Money is an integer in kobo.
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=SettlementStatus.HELD,
        server_default=SettlementStatus.HELD,
        nullable=False,
    )

    # Who released or reversed it, and when.
    actioned_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actioned_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="settlements")
    actioned_by: Mapped[Optional["User"]] = relationship(
        foreign_keys=[actioned_by_user_id]
    )

    def __repr__(self) -> str:
        return f"<Settlement candidate={self.candidate_id} {self.status} {self.amount_kobo}>"
