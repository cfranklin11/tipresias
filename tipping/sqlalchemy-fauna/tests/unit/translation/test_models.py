# pylint: disable=missing-docstring,redefined-outer-name

import sqlparse
from sqlparse import sql as token_groups
import pytest
from sqlalchemy_fauna.fauna.translation import models


column_name = "name"


@pytest.mark.parametrize(
    ["column_sql", "expected_table_name", "expected_alias"],
    [
        (f"users.{column_name}", "users", column_name),
        (column_name, None, column_name),
        (f"users.{column_name} AS user_name", "users", "user_name"),
    ],
)
def test_column(column_sql, expected_table_name, expected_alias):
    sql_query = f"SELECT {column_sql} FROM users"
    statement = sqlparse.parse(sql_query)[0]
    idx, column_identifier = statement.token_next_by(i=(token_groups.Identifier))
    _, table_identifier = statement.token_next_by(i=(token_groups.Identifier), idx=idx)

    column = models.Column(column_identifier)

    assert column.name == column_name
    assert str(column) == column_name
    assert column.table_name == expected_table_name
    assert column.alias == expected_alias
    assert column.alias_map == {column.name: column.alias}

    table = models.Table(table_identifier, columns=[column])
    column.table = table
    assert column.table_name == table.name


table_name = "users"
select_single_column = f"SELECT {table_name}.id FROM {table_name}"
select_columns = f"SELECT {table_name}.id, {table_name}.name FROM {table_name}"
select_aliases = (
    f"SELECT {table_name}.id AS user_id, {table_name}.name AS user_name "
    "FROM {table_name}"
)
select_function = f"SELECT count({table_name}.id) FROM {table_name}"
select_function_alias = (
    f"SELECT count({table_name}.id) AS count_{table_name} FROM {table_name}"
)
insert = "INSERT INTO users (name, age, finger_count) VALUES ('Bob', 30, 10)"


@pytest.mark.parametrize(
    ["sql_query", "expected_columns", "expected_aliases"],
    [
        (select_single_column, ["ref"], ["id"]),
        (select_columns, ["ref", "name"], ["id", "name"]),
        (select_aliases, ["ref", "name"], ["user_id", "user_name"]),
        (select_function, [f"count({table_name}.id)"], [f"count({table_name}.id)"]),
        (select_function_alias, [f"count({table_name}.id)"], [f"count_{table_name}"]),
        (insert, ["name", "age", "finger_count"], ["name", "age", "finger_count"]),
    ],
)
def test_from_identifier_group(sql_query, expected_columns, expected_aliases):
    statement = sqlparse.parse(sql_query)[0]
    _, identifiers = statement.token_next_by(
        i=(token_groups.Identifier, token_groups.IdentifierList, token_groups.Function)
    )

    columns = models.Column.from_identifier_group(identifiers)

    for column in columns:
        assert column.name in expected_columns
        assert column.alias in expected_aliases


def test_table():
    table_name = "users"
    sql_query = f"SELECT users.name FROM {table_name}"
    statement = sqlparse.parse(sql_query)[0]
    idx, column_identifier = statement.token_next_by(i=(token_groups.Identifier))
    _, table_identifier = statement.token_next_by(i=(token_groups.Identifier), idx=idx)

    column = models.Column(column_identifier)
    table = models.Table(table_identifier, columns=[column])
    assert table.name == table_name
    assert str(table) == table_name

    assert len(table.columns) == 1
    assert table.columns[0].name == column.name
    assert table.column_alias_map == {column.name: column.alias}


def test_add_column():
    table_name = "users"
    sql_query = f"SELECT users.name FROM {table_name}"
    statement = sqlparse.parse(sql_query)[0]
    idx, column_identifier = statement.token_next_by(i=(token_groups.Identifier))
    _, table_identifier = statement.token_next_by(i=(token_groups.Identifier), idx=idx)

    column = models.Column(column_identifier)
    table = models.Table(table_identifier)

    table.add_column(column)

    assert table.columns == [column]
