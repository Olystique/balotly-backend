"""Model registry.

alembic/env.py does ``from api.v1.models import *`` to populate
``Base.metadata`` before autogenerate runs. Any new model MUST be imported and
listed in ``__all__`` here, or Alembic will silently generate an empty
migration — or worse, a DROP.
"""

from api.v1.models.base_model import BaseTableModel
from api.v1.models.candidate import Candidate, CandidateStatus
from api.v1.models.category import Category
from api.v1.models.contest import Contest, ContestStatus
from api.v1.models.organization import Organization
from api.v1.models.settlement import Settlement, SettlementStatus
from api.v1.models.subaccount import Subaccount, SubaccountStatus
from api.v1.models.transaction import Transaction, TransactionStatus
from api.v1.models.user import User, UserRole
from api.v1.models.vote import Vote
from api.v1.models.vote_package import VotePackage

__all__ = [
    "BaseTableModel",
    "Candidate",
    "CandidateStatus",
    "Category",
    "Contest",
    "ContestStatus",
    "Organization",
    "Settlement",
    "SettlementStatus",
    "Subaccount",
    "SubaccountStatus",
    "Transaction",
    "TransactionStatus",
    "User",
    "UserRole",
    "Vote",
    "VotePackage",
]
