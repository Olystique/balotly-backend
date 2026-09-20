"""A payment attempt against a vote package.

``paystack_reference`` is unique, and that is the idempotency key for the
whole payment system: Paystack redelivers webhooks, and a redelivery must find
the row it already credited and do nothing (BE-10).

Every foreign key here is RESTRICT rather than CASCADE. A transaction is a
financial record; deleting a candidate or a package must not silently erase
the evidence of who paid what.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate
    from api.v1.models.contest import Contest
    from api.v1.models.vote import Vote
    from api.v1.models.vote_package import VotePackage


class TransactionStatus:
    # Row created before the redirect to Paystack, so a webhook arriving later
    # always has something to match (BE-09).
    PENDING = "pending"
    # ``charge.success`` verified and votes inserted, in one DB transaction.
    SUCCESS = "success"
    FAILED = "failed"

    ALL = (PENDING, SUCCESS, FAILED)


class Transaction(BaseTableModel):
    __tablename__ = "transactions"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'success', 'failed')",
            name="ck_transactions_status",
        ),
        CheckConstraint("amount_kobo > 0", name="ck_transactions_amount_positive"),
        # A success is a confirmed success.
        CheckConstraint(
            "status <> 'success' OR confirmed_at IS NOT NULL",
            name="ck_transactions_success_is_confirmed",
        ),
        # A row cannot claim to enforce the cap without an identity to cap.
        CheckConstraint(
            "NOT enforce_identity_cap OR voter_matric_number IS NOT NULL",
            name="ck_transactions_cap_needs_matric_number",
        ),
        # One vote per matric number per contest, only where the contest asks
        # for it (BE-01 note, §7). Partial, so pageant-style contests keep
        # allowing repeats; the flag is copied from the contest at checkout,
        # which is the only way a per-contest rule can be an index predicate.
        #
        # Pending rows count. BE-09 promises the duplicate is rejected before
        # any Paystack call, and two concurrent checkouts for the same number
        # can only be stopped at insert time, before either voter has paid. A
        # checkout that was abandoned holds the number until it is marked
        # failed, which is BE-09's job to do on a schedule.
        Index(
            "uq_transactions_identity_cap",
            "contest_id",
            "voter_matric_number",
            unique=True,
            postgresql_where=text(
                "enforce_identity_cap AND status IN ('pending', 'success')"
            ),
        ),
        # The candidate dashboard's revenue query and the leaderboard cache.
        Index("ix_transactions_candidate_status", "candidate_id", "status"),
        Index("ix_transactions_contest_status", "contest_id", "status"),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    vote_package_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("vote_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Reachable through candidate -> category -> contest, but denormalised
    # because the identity cap is a unique index over (contest, matric
    # number) and an index cannot follow a join.
    contest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contests.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    paystack_reference: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, nullable=False
    )
    # Copied from the package at checkout. Money is an integer in kobo.
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=TransactionStatus.PENDING,
        server_default=TransactionStatus.PENDING,
        nullable=False,
    )

    voter_matric_number: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )
    voter_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    # Snapshot of ``contest.caps_votes_per_identity`` at checkout; the
    # predicate of the partial unique index above.
    enforce_identity_cap: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    confirmed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="transactions")
    vote_package: Mapped["VotePackage"] = relationship(
        back_populates="transactions"
    )
    contest: Mapped["Contest"] = relationship()
    votes: Mapped[list["Vote"]] = relationship(back_populates="transaction")

    def __repr__(self) -> str:
        return f"<Transaction {self.paystack_reference} {self.status}>"
