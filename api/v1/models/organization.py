"""The client running things: a school's electoral body, an awards committee
(BALOTLY_PROJECT_SPEC.md §4)."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.contest import Contest
    from api.v1.models.user import User


class Organization(BaseTableModel):
    __tablename__ = "organizations"

    __table_args__ = (
        CheckConstraint(
            "platform_fee_percent IS NULL "
            "OR (platform_fee_percent >= 0 AND platform_fee_percent <= 100)",
            name="ck_organizations_platform_fee_percent_range",
        ),
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    contact_email: Mapped[Optional[str]] = mapped_column(
        String(320), nullable=True
    )
    contact_phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

    # Override of the platform-wide default fee. Null means "use the default".
    #
    # A percentage, not money, so the integer-kobo rule does not apply; it is
    # kept as a fixed-point decimal because it goes to Paystack verbatim as
    # ``percentage_charge`` and a float would round it before it got there.
    platform_fee_percent: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )

    # The organizer who created it. Nullable and SET NULL rather than
    # CASCADE: an organization outlives the account of whoever set it up.
    # ``use_alter`` because users also point at organizations, and one of
    # the two foreign keys has to be added after both tables exist.
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "users.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_organizations_created_by_user_id_users",
        ),
        nullable=True,
    )

    users: Mapped[list["User"]] = relationship(
        back_populates="organization", foreign_keys="User.organization_id"
    )
    contests: Mapped[list["Contest"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Organization {self.name}>"
