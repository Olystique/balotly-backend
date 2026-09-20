"""One event or season: "2026 SUG Elections", "2026 Award Night"."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.category import Category
    from api.v1.models.organization import Organization
    from api.v1.models.vote_package import VotePackage


class ContestStatus:
    """One-directional: draft -> active -> closed. A closed contest is never
    reopened; the organizer creates a new one (BE-03)."""

    DRAFT = "draft"
    ACTIVE = "active"
    CLOSED = "closed"

    ALL = (DRAFT, ACTIVE, CLOSED)


class Contest(BaseTableModel):
    __tablename__ = "contests"

    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'active', 'closed')",
            name="ck_contests_status",
        ),
        CheckConstraint("ends_at > starts_at", name="ck_contests_window"),
        CheckConstraint(
            "platform_fee_percent IS NULL "
            "OR (platform_fee_percent >= 0 AND platform_fee_percent <= 100)",
            name="ck_contests_platform_fee_percent_range",
        ),
        # The organizer dashboard's listing and the public "is voting open"
        # checks both filter on these two.
        Index("ix_contests_organization_status", "organization_id", "status"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        default=ContestStatus.DRAFT,
        server_default=ContestStatus.DRAFT,
        nullable=False,
    )

    # School mode: the voter is asked for a matric number at checkout.
    requires_matric_number: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    # Whether that matric number may vote only once in this contest.
    #
    # Separate from ``requires_matric_number`` because the two integrity
    # models in §7 are different products: a school election caps one vote
    # per identity, while a pageant that merely collects an identifier for
    # analytics must keep allowing repeats. BE-09 checks both. The cap itself
    # is enforced by a partial unique index on ``transactions``.
    caps_votes_per_identity: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )

    # Per-contest override of the organization's fee, itself an override of
    # the platform default (BE-06 reads "the organization's or contest's
    # configured platform fee"). Null means "inherit".
    platform_fee_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ends_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="contests")
    categories: Mapped[list["Category"]] = relationship(
        back_populates="contest", cascade="all, delete-orphan"
    )
    vote_packages: Mapped[list["VotePackage"]] = relationship(
        back_populates="contest", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Contest {self.name} {self.status}>"
