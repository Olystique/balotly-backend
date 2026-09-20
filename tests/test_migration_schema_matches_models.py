"""The migrations must actually produce the schema the ORM assumes.

Every other suite here talks to a fake session, so nothing in them ever emits
real DDL or a real INSERT. A column the ORM believes the database will
populate, but which the database has no default for, fails only when a row is
actually written; with no live-database tests that means production.

Alembic's offline mode renders the whole migration history as SQL text, which
is enough to check that what the migrations build matches what the models
declare, without needing a database.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from api.db.database import Base

# Importing the package is what registers every table on Base.metadata. Without
# it the checks below inspect an empty schema and pass without testing
# anything, which is why they assert the model set is non-empty first.
import api.v1.models  # noqa: F401

_REPO_ROOT = Path(__file__).resolve().parent.parent

# Offline rendering never opens a connection (see alembic/env.py), but the URL
# still has to parse. Pointed at a closed port so a regression that tries to
# connect fails loudly here instead of reaching real infrastructure.
_UNUSED_URL = "postgresql://unused:unused@127.0.0.1:1/unused"


@pytest.fixture(scope="session")
def rendered_ddl() -> str:
    """Every migration from base to head, as SQL text."""
    try:
        result = subprocess.run(
            ["alembic", "upgrade", "base:head", "--sql"],
            capture_output=True,
            text=True,
            cwd=_REPO_ROOT,
            env={**os.environ, "DB_URL": _UNUSED_URL},
            timeout=180,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"alembic unavailable: {exc}")

    if result.returncode != 0:
        pytest.fail(
            "Could not render the migrations offline. That is itself a "
            f"problem worth fixing.\n{result.stderr[-2000:]}"
        )
    return result.stdout


def _columns_created_with_a_default(ddl: str) -> set[tuple[str, str]]:
    """Columns whose CREATE TABLE line carries an inline DEFAULT."""
    found = set()
    for table, body in re.findall(
        r"CREATE TABLE (\w+) \((.*?)\n\);", ddl, re.DOTALL
    ):
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            match = re.match(r"^(\w+)\s+.*\bDEFAULT\b", line, re.IGNORECASE)
            if match:
                found.add((table, match.group(1)))
    return found


def _columns_given_a_default_later(ddl: str) -> set[tuple[str, str]]:
    """Columns given a default after the table existed."""
    added = {
        (table, column)
        for table, column in re.findall(
            r"ALTER TABLE (\w+)\s+ADD COLUMN (\w+)[^;]*?\bDEFAULT\b",
            ddl,
            re.IGNORECASE,
        )
    }
    altered = {
        (table, column)
        for table, column in re.findall(
            r"ALTER TABLE (\w+) ALTER COLUMN (\w+) SET DEFAULT", ddl
        )
    }
    return added | altered


def _columns_stripped_of_their_default(ddl: str) -> set[tuple[str, str]]:
    return {
        (table, column)
        for table, column in re.findall(
            r"ALTER TABLE (\w+) ALTER COLUMN (\w+) DROP DEFAULT", ddl
        )
    }


def _model_columns_declaring_a_server_default() -> set[tuple[str, str]]:
    return {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.server_default is not None
    }


def test_every_server_default_in_the_models_exists_in_the_schema(rendered_ddl):
    expected = _model_columns_declaring_a_server_default()
    assert expected, "no server defaults found; the check would be vacuous"

    present = (
        _columns_created_with_a_default(rendered_ddl)
        | _columns_given_a_default_later(rendered_ddl)
    ) - _columns_stripped_of_their_default(rendered_ddl)

    missing = sorted(expected - present)
    assert not missing, (
        "These columns declare server_default in the model but the migrations "
        "never give the database one, so any insert that omits them fails "
        f"with a NOT NULL violation: {missing}"
    )


def test_every_model_table_is_actually_created(rendered_ddl):
    """A model with no migration behind it is the same class of failure,
    found the same way: only when a query runs."""
    created = set(re.findall(r"CREATE TABLE (\w+)", rendered_ddl))
    missing = sorted(set(Base.metadata.tables) - created - {"alembic_version"})
    assert not missing, f"models with no CREATE TABLE in any migration: {missing}"


def test_the_parser_notices_a_missing_default_on_an_added_column(rendered_ddl):
    """Guards the check above from quietly accepting everything."""
    fabricated = rendered_ddl + "\nALTER TABLE widgets ADD COLUMN colour VARCHAR;"
    assert ("widgets", "colour") not in _columns_given_a_default_later(fabricated)

    with_default = fabricated + "\nALTER TABLE widgets ADD COLUMN size INTEGER DEFAULT '1' NOT NULL;"
    assert ("widgets", "size") in _columns_given_a_default_later(with_default)


def test_every_index_compiles_to_real_ddl():
    """A partial index whose predicate is not a SQL expression.

    ``postgresql_where=Text("status IN (...)")`` imports, type-checks and even
    passes the checks above, because ``Text`` is the *column type* and happily
    accepted the predicate as its length argument. Nothing notices until
    Postgres is asked to build the index.
    """
    from sqlalchemy.dialects import postgresql
    from sqlalchemy.schema import CreateIndex

    dialect = postgresql.dialect()
    for table in Base.metadata.tables.values():
        for index in table.indexes:
            try:
                CreateIndex(index).compile(dialect=dialect)
            except Exception as exc:  # noqa: BLE001 - reported, not swallowed
                pytest.fail(f"{table.name}.{index.name} will not build: {exc}")


def _columns_in_the_rendered_schema(ddl: str) -> set[tuple[str, str]]:
    """Every column the migrations create, whether at table creation or after.

    Dropped columns are removed again, so a column added and later dropped is
    correctly reported as absent rather than as present.
    """
    found: set[tuple[str, str]] = set()
    for table, body in re.findall(
        r"CREATE TABLE (\w+) \((.*?)\n\);", ddl, re.DOTALL
    ):
        for line in body.split("\n"):
            line = line.strip().rstrip(",")
            # Skip table-level constraints, which are not columns.
            if re.match(
                r"^(PRIMARY|FOREIGN|UNIQUE|CHECK|CONSTRAINT)\b", line, re.IGNORECASE
            ):
                continue
            match = re.match(r"^(\w+)\s+\S", line)
            if match:
                found.add((table, match.group(1)))

    for table, column in re.findall(
        r"ALTER TABLE (\w+)\s+ADD COLUMN (?:IF NOT EXISTS\s+)?(\w+)",
        ddl,
        re.IGNORECASE,
    ):
        found.add((table, column))
    for table, column in re.findall(
        r"ALTER TABLE (\w+)\s+DROP COLUMN (?:IF EXISTS\s+)?(\w+)",
        ddl,
        re.IGNORECASE,
    ):
        found.discard((table, column))
    return found


def test_every_model_column_exists_in_the_schema(rendered_ddl):
    expected = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
    }
    assert expected, "no model columns found; the check would be vacuous"

    missing = sorted(expected - _columns_in_the_rendered_schema(rendered_ddl))
    assert not missing, (
        "These columns exist in the models but no migration creates them, so "
        f"every query naming them fails against a real database: {missing}"
    )


def test_no_schema_column_is_missing_from_the_models(rendered_ddl):
    """The other direction: a column the migration creates that no model
    knows about is drift the ORM will never read or write."""
    declared = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
    }
    rendered = {
        (table, column)
        for table, column in _columns_in_the_rendered_schema(rendered_ddl)
        if table != "alembic_version"
    }
    extra = sorted(rendered - declared)
    assert not extra, f"columns in the migrations with no model behind them: {extra}"


def test_the_column_parser_notices_an_absence(rendered_ddl):
    """Guards the check above from being a rubber stamp."""
    columns = _columns_in_the_rendered_schema(rendered_ddl)
    assert ("transactions", "paystack_reference") in columns
    assert ("votes", "candidate_id") in columns
    assert ("votes", "no_such_column") not in columns

    dropped = _columns_in_the_rendered_schema(
        rendered_ddl + "\nALTER TABLE transactions DROP COLUMN voter_phone;"
    )
    assert ("transactions", "voter_phone") not in dropped
