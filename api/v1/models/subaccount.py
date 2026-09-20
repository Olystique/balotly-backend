"""The Paystack subaccount that a candidate's share settles to (§6, BE-06).

One per candidate, not per organizer or contest: the money is explicitly for
the contestant. ``settlement_schedule`` is ``manual`` so funds are held until
an organizer or admin releases them (BE-15), which is what lets a
disqualification withhold a payout before it leaves the platform.
"""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import CheckConstraint, ForeignKey, LargeBinary, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from api.v1.models.base_model import BaseTableModel

if TYPE_CHECKING:
    from api.v1.models.candidate import Candidate


class SubaccountStatus:
    # Bank details submitted; the Paystack subaccount does not exist yet, or
    # its creation failed and can be retried.
    PENDING = "pending"
    # Account name resolved, subaccount created, code stored.
    VERIFIED = "verified"

    ALL = (PENDING, VERIFIED)


class Subaccount(BaseTableModel):
    __tablename__ = "subaccounts"

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'verified')", name="ck_subaccounts_status"
        ),
        # A verified row is one Paystack has actually created.
        CheckConstraint(
            "status <> 'verified' OR subaccount_code IS NOT NULL",
            name="ck_subaccounts_verified_has_code",
        ),
        CheckConstraint(
            "percentage_charge IS NULL "
            "OR (percentage_charge >= 0 AND percentage_charge <= 100)",
            name="ck_subaccounts_percentage_charge_range",
        ),
    )

    candidate_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("candidates.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )

    bank_code: Mapped[str] = mapped_column(String(16), nullable=False)
    # AES-GCM ciphertext from api.core.security.encrypt_str. Needed in the
    # clear only for the resolve and create calls to Paystack.
    account_number_encrypted: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False
    )
    # What Paystack's resolve-account-number returned, shown back to the
    # candidate for confirmation before anything is created (BE-06 step 3).
    account_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    subaccount_code: Mapped[Optional[str]] = mapped_column(
        String(64), unique=True, nullable=True
    )
    # The platform fee this subaccount was created with. A snapshot: the
    # organization's setting can change afterwards, and what Paystack applies
    # is what was sent at creation, not what the settings say now.
    percentage_charge: Mapped[Optional[Decimal]] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    settlement_schedule: Mapped[str] = mapped_column(
        String(16), default="manual", server_default="manual", nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(32),
        default=SubaccountStatus.PENDING,
        server_default=SubaccountStatus.PENDING,
        nullable=False,
    )

    candidate: Mapped["Candidate"] = relationship(back_populates="subaccount")

    def __repr__(self) -> str:
        return f"<Subaccount candidate={self.candidate_id} {self.status}>"
