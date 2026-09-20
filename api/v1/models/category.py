"""A position or award within a contest: "Best Social Director"."""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate
    from api.v1.models.contest import Contest


class Category(BaseTableModel):
    __tablename__ = "categories"

    __table_args__ = (
        # Two "Best Social Director" positions in one contest is a typo, and
        # the leaderboard groups by category, so it would show as a split.
        UniqueConstraint("contest_id", "name", name="uq_categories_contest_name"),
    )

    contest_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("contests.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    contest: Mapped["Contest"] = relationship(back_populates="categories")
    candidates: Mapped[list["Candidate"]] = relationship(
        back_populates="category", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Category {self.name}>"
