"""Accounts that sign in: platform admins, organizers and candidates
(BALOTLY_PROJECT_SPEC.md §3). Voters never have one."""

import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate
    from api.v1.models.organization import Organization


class UserRole:
    """Plain strings rather than a native PG enum, so adding a role later is
    a no-op instead of an ALTER TYPE migration."""

    # Olystique staff: every organization, platform-wide revenue, abuse.
    ADMIN = "admin"
    # Runs contests for exactly one organization.
    ORGANIZER = "organizer"
    # The person being voted for.
    CANDIDATE = "candidate"

    ALL = (ADMIN, ORGANIZER, CANDIDATE)


class User(BaseTableModel):
    __tablename__ = "users"

    __table_args__ = (
        CheckConstraint(
            "role IN ('admin', 'organizer', 'candidate')",
            name="ck_users_role",
        ),
    )

    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)

    # The tenant an organizer belongs to; carried in their JWT and applied to
    # every organizer-scoped query (BE-02). Nullable because an organizer
    # signs up first and creates the organization second (§5.1), and because
    # admins and candidates have none.
    organization_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    organization: Mapped[Optional["Organization"]] = relationship(
        back_populates="users", foreign_keys=[organization_id]
    )
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="user", foreign_keys="Candidate.user_id"
    )

    def __repr__(self) -> str:
        return f"<User {self.email} {self.role}>"
