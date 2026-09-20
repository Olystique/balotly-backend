"""One row per unit vote: the append-only ledger.

This table is the single most important design decision in the system
(BALOTLY_PROJECT_SPEC.md §4). A vote count is always ``COUNT(*)`` over these
rows, never a counter column that can drift from the payment log, so "how
many votes does X have" is always reconstructable from confirmed transactions
alone.

Three consequences for the shape of the table:

* No ``updated_at``, and no ``BaseTableModel``. Nothing about a vote ever
  changes after it is written, so a column recording when it changed would
  only ever be a lie.
* Every foreign key is RESTRICT. Deleting a transaction or a candidate must
  not take votes with it; corrections happen through the transaction layer.
* The migration installs triggers that refuse UPDATE, DELETE and TRUNCATE
  on this table outright. The ORM never needs either, and a raw statement that tries
  is a bug, not an administrative action.
"""

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.db.database import Base

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate
    from api.v1.models.transaction import Transaction


class Vote(Base):
    __tablename__ = "votes"

    __table_args__ = (
        # The leaderboard: COUNT(*) per candidate.
        Index("ix_votes_candidate_created", "candidate_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    # Also on the transaction, and deliberately duplicated: the leaderboard
    # counts by candidate, and a count that has to join through transactions
    # on every refresh is the query that falls over at contest close.
    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    transaction: Mapped["Transaction"] = relationship(back_populates="votes")
    candidate: Mapped["Candidate"] = relationship(back_populates="votes")

    def __repr__(self) -> str:
        return f"<Vote candidate={self.candidate_id} tx={self.transaction_id}>"
