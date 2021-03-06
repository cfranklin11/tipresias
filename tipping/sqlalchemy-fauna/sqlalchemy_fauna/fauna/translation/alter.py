"""Translate a ALTER SQL query into an equivalent FQL query."""

import typing

from sqlparse import sql as token_groups
from sqlparse import tokens as token_types
from faunadb import query as q
from faunadb.objects import _Expr as QueryExpression

from sqlalchemy_fauna import exceptions
from .models import Column, Table


def _translate_drop_default(table_name: str, column_name: str) -> QueryExpression:
    drop_default = q.update(
        q.collection(table_name),
        {"data": {"metadata": {"fields": {column_name: {"default": None}}}}},
    )
    select_ref = lambda res: q.select("ref", res)

    return q.let(
        {"collection": select_ref(drop_default)},
        {"data": [{"id": q.var("collection")}]},
    )


def _translate_alter_column(
    statement: token_groups.Statement,
    table: Table,
    starting_idx: int,
) -> QueryExpression:
    idx, column_identifier = statement.token_next_by(
        i=token_groups.Identifier, idx=starting_idx
    )
    column = Column(column_identifier)
    table.add_column(column)

    _, drop = statement.token_next_by(m=(token_types.DDL, "DROP"), idx=idx)
    _, default = statement.token_next_by(m=(token_types.Keyword, "DEFAULT"))

    if drop and default:
        return _translate_drop_default(table.name, table.columns[0].name)

    raise exceptions.NotSupportedError(
        "For statements with ALTER COLUMN, only DROP DEFAULT is currently supported."
    )


def translate_alter(statement: token_groups.Statement) -> typing.List[QueryExpression]:
    """Translate an ALTER SQL query into an equivalent FQL query.

    Params:
    -------
    statement: An SQL statement returned by sqlparse.

    Returns:
    --------
    An FQL query expression.
    """
    idx, table_keyword = statement.token_next_by(m=(token_types.Keyword, "TABLE"))
    assert table_keyword is not None

    idx, table_identifier = statement.token_next_by(i=token_groups.Identifier, idx=idx)
    table = Table(table_identifier)

    _, second_alter = statement.token_next_by(m=(token_types.DDL, "ALTER"), idx=idx)
    _, column_keyword = statement.token_next_by(
        m=(token_types.Keyword, "COLUMN"), idx=idx
    )

    if second_alter and column_keyword:
        return [_translate_alter_column(statement, table, idx)]

    raise exceptions.NotSupportedError(
        "For ALTER TABLE queries, only ALTER COLUMN is currently supported."
    )
