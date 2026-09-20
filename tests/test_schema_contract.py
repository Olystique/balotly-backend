"""BE-01's acceptance criteria, checked against the models and the rendered
migration rather than against a database.

Each test names the criterion it pins. If one of these ever fails, the
migration or the model has drifted from the contract the payment system rests
on, and that is a stop-the-line event, not a refactor.
"""

from __future__ import annotations

import re

import pytest
from sqlalchemy import BigInteger, Boolean, Integer

from api.db.database import Base
from api.v1.models import (
    Candidate,
    Contest,
    Settlement,
    Subaccount,
    Transaction,
    Vote,
    VotePackage,
)
import api.v1.models  # noqa: F401

from tests.test_migration_schema_matches_models import rendered_ddl  # noqa: F401

_SPEC_TABLES = {
    "organizations",
    "users",
    "contests",
    "categories",
    "candidates",
    "vote_packages",
    "transactions",
    "votes",
    "subaccounts",
    "settlements",
}


def _unique_column_sets(table) -> set[frozenset[str]]:
    """Every unique constraint or unique index on a table, by column set."""
    found: set[frozenset[str]] = set()
    for constraint in table.constraints:
        if getattr(constraint, "unique", False) or type(constraint).__name__ == "UniqueConstraint":
            found.add(frozenset(c.name for c in constraint.columns))
    for index in table.indexes:
        if index.unique:
            found.add(frozenset(c.name for c in index.columns))
    return found


def test_all_spec_tables_exist_in_the_models():
    """BE-01: every table in the issue's list exists."""
    assert _SPEC_TABLES <= set(Base.metadata.tables)


def test_all_spec_tables_exist_in_the_migration(rendered_ddl):
    created = set(re.findall(r"CREATE TABLE (\w+)", rendered_ddl))
    assert _SPEC_TABLES <= created


def test_paystack_reference_is_unique():
    """BE-01: the idempotency key for the whole payment system."""
    column = Transaction.__table__.c.paystack_reference
    assert not column.nullable
    assert frozenset({"paystack_reference"}) in _unique_column_sets(
        Transaction.__table__
    )


def test_paystack_reference_is_unique_in_the_migration(rendered_ddl):
    assert re.search(
        r"CREATE UNIQUE INDEX \w+ ON transactions \(paystack_reference\)",
        rendered_ddl,
    )


def test_votes_is_an_append_only_ledger():
    """BE-01: no mutable count field anywhere, one row per unit vote, FK to
    transaction_id and candidate_id."""
    columns = {c.name for c in Vote.__table__.columns}
    assert columns == {"id", "transaction_id", "candidate_id", "created_at"}
    assert not any("count" in name for name in columns)
    # Nothing on a vote changes, so there is nothing an updated_at could
    # truthfully record.
    assert "updated_at" not in columns

    fk_targets = {
        (fk.parent.name, fk.column.table.name) for fk in Vote.__table__.foreign_keys
    }
    assert fk_targets == {
        ("transaction_id", "transactions"),
        ("candidate_id", "candidates"),
    }


def test_votes_cannot_be_updated_or_deleted(rendered_ddl):
    """The trigger that makes the ledger append-only at the database, not
    just by convention."""
    assert "CREATE TRIGGER votes_append_only" in rendered_ddl
    assert re.search(r"BEFORE UPDATE OR DELETE ON votes", rendered_ddl)
    # Row triggers do not fire on TRUNCATE; it needs a statement trigger.
    assert "CREATE TRIGGER votes_no_truncate" in rendered_ddl
    assert re.search(r"BEFORE TRUNCATE ON votes", rendered_ddl)


def test_ledger_foreign_keys_never_cascade():
    """Deleting a candidate or a transaction must not delete payment
    evidence. Corrections go through the transaction layer."""
    for table in (Vote.__table__, Transaction.__table__, Settlement.__table__):
        for fk in table.foreign_keys:
            if fk.column.table.name == "users":
                continue  # who acted, not what happened; SET NULL is right
            assert fk.ondelete == "RESTRICT", (
                f"{table.name}.{fk.parent.name} -> {fk.column.table.name} "
                f"is {fk.ondelete}, not RESTRICT"
            )


def test_candidate_slug_is_unique_and_required():
    """BE-01: candidates has a unique slug used in the public vote URL."""
    column = Candidate.__table__.c.slug
    assert not column.nullable
    assert frozenset({"slug"}) in _unique_column_sets(Candidate.__table__)


def test_identity_cap_is_a_partial_unique_index():
    """BE-01 note: (contest_id, voter_matric_number) is unique on
    transactions only when the contest asks for it, never globally, so
    pageant-style contests keep allowing repeats."""
    index = next(
        i for i in Transaction.__table__.indexes
        if i.name == "uq_transactions_identity_cap"
    )
    assert index.unique
    assert [c.name for c in index.columns] == ["contest_id", "voter_matric_number"]
    predicate = str(index.dialect_options["postgresql"]["where"])
    assert "enforce_identity_cap" in predicate
    # A global constraint would have no predicate at all.
    assert predicate.strip()


def test_identity_cap_predicate_is_in_the_migration(rendered_ddl):
    match = re.search(
        r"CREATE UNIQUE INDEX uq_transactions_identity_cap ON transactions "
        r"\(contest_id, voter_matric_number\) WHERE (.+)",
        rendered_ddl,
    )
    assert match, "partial unique index missing from the rendered schema"
    assert "enforce_identity_cap" in match.group(1)


def test_contest_carries_both_identity_flags():
    """Requiring a matric number and capping votes per identity are two
    settings (BE-09 checks them separately)."""
    columns = Contest.__table__.c
    assert isinstance(columns.requires_matric_number.type, Boolean)
    assert isinstance(columns.caps_votes_per_identity.type, Boolean)
    assert not columns.requires_matric_number.nullable
    assert not columns.caps_votes_per_identity.nullable


@pytest.mark.parametrize(
    "table, column",
    [
        (VotePackage.__table__, "amount_kobo"),
        (Transaction.__table__, "amount_kobo"),
        (Settlement.__table__, "amount_kobo"),
    ],
)
def test_money_is_a_big_integer_in_kobo(table, column):
    """Cross-cutting: money is always an integer, never a float, and kobo
    overflows 32 bits at about 21 million naira."""
    col = table.c[column]
    assert isinstance(col.type, BigInteger)
    assert not col.nullable


def test_vote_count_is_a_positive_integer():
    col = VotePackage.__table__.c.vote_count
    assert isinstance(col.type, Integer)
    assert not col.nullable
    names = {c.name for c in VotePackage.__table__.constraints}
    assert "ck_vote_packages_votes_positive" in names
    assert "ck_vote_packages_amount_positive" in names


def test_no_table_stores_money_as_a_float():
    from sqlalchemy import Float, Numeric

    for table in Base.metadata.tables.values():
        for column in table.columns:
            if "kobo" in column.name or "amount" in column.name:
                assert not isinstance(column.type, (Float, Numeric)), (
                    f"{table.name}.{column.name} is {column.type}"
                )


def test_disqualification_requires_a_reason():
    """BE-05's audit requirement, enforced at the database."""
    names = {c.name for c in Candidate.__table__.constraints}
    assert "ck_candidates_disqualified_has_reason" in names


def test_one_subaccount_per_candidate():
    """§6: one subaccount per candidate, not per organizer or contest."""
    assert frozenset({"candidate_id"}) in _unique_column_sets(Subaccount.__table__)


def test_required_fields_are_not_null():
    """BE-01: NOT NULL on required fields. The spot checks that matter most."""
    required = [
        ("users", "email"),
        ("users", "password_hash"),
        ("users", "role"),
        ("organizations", "name"),
        ("contests", "organization_id"),
        ("contests", "name"),
        ("contests", "status"),
        ("contests", "starts_at"),
        ("contests", "ends_at"),
        ("categories", "contest_id"),
        ("categories", "name"),
        ("candidates", "category_id"),
        ("candidates", "name"),
        ("candidates", "status"),
        ("vote_packages", "contest_id"),
        ("vote_packages", "label"),
        ("transactions", "candidate_id"),
        ("transactions", "vote_package_id"),
        ("transactions", "contest_id"),
        ("transactions", "status"),
        ("subaccounts", "candidate_id"),
        ("subaccounts", "bank_code"),
        ("subaccounts", "account_number_encrypted"),
        ("settlements", "candidate_id"),
        ("settlements", "period_start"),
        ("settlements", "period_end"),
        ("settlements", "status"),
    ]
    for table, column in required:
        assert not Base.metadata.tables[table].c[column].nullable, (
            f"{table}.{column} must be NOT NULL"
        )


def test_every_foreign_key_in_the_models_is_in_the_migration(rendered_ddl):
    """BE-01: appropriate foreign keys. Every FK the ORM relies on must be
    one the database actually enforces."""
    rendered = set()
    for table, body in re.findall(r"CREATE TABLE (\w+) \((.*?)\n\);", rendered_ddl, re.DOTALL):
        for col, target in re.findall(
            r"FOREIGN KEY\((\w+)\) REFERENCES (\w+)", body
        ):
            rendered.add((table, col, target))
    for table, col, target in re.findall(
        r"ALTER TABLE (\w+) ADD CONSTRAINT \w+ FOREIGN KEY\s*\((\w+)\) REFERENCES (\w+)",
        rendered_ddl,
    ):
        rendered.add((table, col, target))

    expected = {
        (fk.parent.table.name, fk.parent.name, fk.column.table.name)
        for table in Base.metadata.tables.values()
        for fk in table.foreign_keys
    }
    missing = sorted(expected - rendered)
    assert not missing, f"foreign keys in the models but not the migration: {missing}"
