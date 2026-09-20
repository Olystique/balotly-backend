"""A priced tier, defined per contest: N100 = 1 vote, N500 = 5 votes.

Per contest, never hardcoded: the N100/N500/N1000 tiers on the reference
poster are a suggestion the organizer can change (BE-04).
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.contest import Contest
    from api.v1.models.transaction import Transaction


class VotePackage(BaseTableModel):
    __tablename__ = "vote_packages"

    __table_args__ = (
        CheckConstraint("amount_kobo > 0", name="ck_vote_packages_amount_positive"),
        CheckConstraint("vote_count > 0", name="ck_vote_packages_votes_positive"),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Money is always an integer in kobo, never a float. BigInteger because
    # kobo overflows 32 bits at about 21 million naira.
    amount_kobo: Mapped[int] = mapped_column(BigInteger, nullable=False)
    vote_count: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)

    contest: Mapped["Contest"] = relationship(back_populates="vote_packages")
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="vote_package"
    )

    def __repr__(self) -> str:
        return f"<VotePackage {self.label} {self.amount_kobo}k={self.vote_count}>"
