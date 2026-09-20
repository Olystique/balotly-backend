"""The person being voted for. Belongs to exactly one category."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.category import Category
    from api.v1.models.settlement import Settlement
    from api.v1.models.subaccount import Subaccount
    from api.v1.models.transaction import Transaction
    from api.v1.models.user import User
    from api.v1.models.vote import Vote


class CandidateStatus:
    """pending_approval -> approved -> (optionally) disqualified (BE-05).

    A candidate receives votes only while ``approved``.
    """

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    DISQUALIFIED = "disqualified"

    ALL = (PENDING_APPROVAL, APPROVED, DISQUALIFIED)


class Candidate(BaseTableModel):
    __tablename__ = "candidates"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'disqualified')",
            name="ck_candidates_status",
        ),
        # BE-05: disqualification always carries a reason, for the audit
        # trail that settlement reversal (BE-15) reads. Enforced here so no
        # code path, including a raw UPDATE, can drop it.
        CheckConstraint(
            "status <> 'disqualified' OR disqualification_reason IS NOT NULL",
            name="ck_candidates_disqualified_has_reason",
        ),
        # The organizer's approval queue.
        Index("ix_candidates_category_status", "category_id", "status"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # The account that can see this candidate's own numbers (BE-02). Nullable
    # because an organizer may add candidates directly (§5.1 step 5), and
    # SET NULL because the record, its votes and its money outlive a deleted
    # login.
    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    # The public vote URL is /vote/:slug. Name-based with a collision suffix
    # (``toheeb-adeoye``, ``toheeb-adeoye-2``); BE-05 generates it.
    slug: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    photo_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    bio: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # The candidate's own matric number, in school mode. Distinct from the
    # voter's, which lives on the transaction.
    matric_number: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    # Set by the poster service (BE-07) once, on approval.
    poster_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(
        String(32),
        default=CandidateStatus.PENDING_APPROVAL,
        server_default=CandidateStatus.PENDING_APPROVAL,
        nullable=False,
    )
    disqualification_reason: Mapped[Optional[str]] = mapped_column(
        Text, nullable=True
    )

    category: Mapped["Category"] = relationship(back_populates="candidates")
    user: Mapped[Optional["User"]] = relationship(
        back_populates="candidates", foreign_keys=[user_id]
    )
    # One Paystack subaccount per candidate (§6). ``uselist=False`` because
    # the table carries a unique constraint on candidate_id.
    subaccount: Mapped[Optional["Subaccount"]] = relationship(
        back_populates="candidate", uselist=False, cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        back_populates="candidate"
    )
    votes: Mapped[list["Vote"]] = relationship(back_populates="candidate")
    settlements: Mapped[list["Settlement"]] = relationship(
        back_populates="candidate"
    )

    def __repr__(self) -> str:
        return f"<Candidate {self.slug} {self.status}>"
