"""Translate a CREATE SQL query into an equivalent FQL query."""

from typing import Dict, Union, List, Optional
from datetime import datetime
from functools import reduce
from copy import deepcopy

from sqlparse import tokens as token_types
from sqlparse import sql as token_groups
from faunadb import query as q
from faunadb.objects import _Expr as QueryExpression
from mypy_extensions import TypedDict

from sqlalchemy_fauna import exceptions
from .common import extract_value


FieldMetadata = TypedDict(
    "FieldMetadata",
    {
        "unique": bool,
        "not_null": bool,
        "default": Union[str, int, float, bool, datetime, None],
        "type": str,
    },
)
FieldsMetadata = Dict[str, FieldMetadata]
CollectionMetadata = TypedDict("CollectionMetadata", {"fields": FieldsMetadata})

DEFAULT_FIELD_METADATA: FieldMetadata = {
    "unique": False,
    "not_null": False,
    "default": None,
    "type": "",
}

DATA_TYPE_MAP = {
    "CHAR": "String",
    "VARCHAR": "String",
    "BINARY": "String",
    "VARBINARY": "String",
    "TINYBLOB": "String",
    "TINYTEXT": "String",
    "TEXT": "String",
    "BLOB": "String",
    "MEDIUMTEXT": "String",
    "MEDIUMBLOB": "String",
    "LONGTEXT": "String",
    "LONGBLOB": "String",
    "ENUM": "String",
    "SET": "String",
    "BIT": "Integer",
    "TINYINT": "Integer",
    "SMALLINT": "Integer",
    "MEDIUMINT": "Integer",
    "INT": "Integer",
    "INTEGER": "Integer",
    "BIGINT": "Integer",
    "FLOAT": "Float",
    "DOUBLE": "Float",
    "DOUBLE PRECISION": "Float",
    "DECIMAL": "Float",
    "DEC": "Float",
    "BOOL": "Boolean",
    "BOOLEAN": "Boolean",
    "YEAR": "Integer",
    "DATE": "Date",
    "DATETIME": "TimeStamp",
    "TIMESTAMP": "TimeStamp",
    # Fauna has no concept of time independent of the date
    "TIME": "String",
}


def _contains_column_name(
    token_group: Union[
        token_groups.TokenList,
        token_groups.IdentifierList,
        token_groups.Identifier,
        token_groups.Parenthesis,
    ],
    idx: int,
) -> bool:
    return token_group.token_next_by(t=token_types.Name, idx=idx) != (None, None)


def _define_primary_key(
    metadata: FieldsMetadata,
    column_definition_group: token_groups.TokenList,
) -> Optional[FieldsMetadata]:
    idx, constraint_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "CONSTRAINT")
    )

    idx, primary_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "PRIMARY"), idx=(idx or -1)
    )

    if constraint_keyword is not None and primary_keyword is None:
        raise exceptions.NotSupportedError(
            "When a column definition clause begins with CONSTRAINT, "
            "only a PRIMARY KEY constraint is supported"
        )

    if primary_keyword is None:
        return None

    # If the keyword isn't followed by column name(s), then it's part of
    # a regular column definition and should be handled by _define_column
    if not _contains_column_name(column_definition_group, idx):
        return None

    new_metadata: FieldsMetadata = deepcopy(metadata)

    while True:
        idx, primary_key_column = column_definition_group.token_next_by(
            t=token_types.Name, idx=idx
        )

        # 'id' is defined and managed by Fauna, so we ignore any attempts
        # to manage it from SQLAlchemy
        if primary_key_column is None or primary_key_column.value == "id":
            break

        primary_key_column_name = primary_key_column.value

        new_metadata[primary_key_column_name] = {
            **DEFAULT_FIELD_METADATA,  # type: ignore
            **new_metadata.get(primary_key_column_name, {}),  # type: ignore
            "unique": True,
            "not_null": True,
        }

    return new_metadata


def _define_unique_constraint(
    metadata: FieldsMetadata,
    column_definition_group: token_groups.TokenList,
) -> Optional[FieldsMetadata]:
    idx, unique_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "UNIQUE")
    )

    if unique_keyword is None:
        return None

    # If the keyword isn't followed by column name(s), then it's part of
    # a regular column definition and should be handled by _define_column
    if not _contains_column_name(column_definition_group, idx):
        return None

    new_metadata = deepcopy(metadata)

    while True:
        idx, unique_key_column = column_definition_group.token_next_by(
            t=token_types.Name, idx=idx
        )

        # 'id' is defined and managed by Fauna, so we ignore any attempts
        # to manage it from SQLAlchemy
        if unique_key_column is None or unique_key_column.value == "id":
            break

        unique_key_column_name = unique_key_column.value

        new_metadata[unique_key_column_name] = {
            **DEFAULT_FIELD_METADATA,  # type: ignore
            **new_metadata.get(unique_key_column_name, {}),  # type: ignore
            "unique": True,
        }

    return new_metadata


def _define_foreign_key_constraint(
    metadata: FieldsMetadata, column_definition_group: token_groups.TokenList
) -> Optional[FieldsMetadata]:
    idx, foreign_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "FOREIGN")
    )
    if foreign_keyword is None:
        return None

    idx, _ = column_definition_group.token_next_by(m=(token_types.Name, "KEY"), idx=idx)
    idx, foreign_key_column = column_definition_group.token_next_by(
        t=token_types.Name, idx=idx
    )
    column_name = foreign_key_column.value

    idx, _ = column_definition_group.token_next_by(
        m=(token_types.Keyword, "REFERENCES"), idx=idx
    )
    idx, reference_table = column_definition_group.token_next_by(
        t=token_types.Name, idx=idx
    )
    reference_table_name = reference_table.value
    idx, reference_column = column_definition_group.token_next_by(
        t=token_types.Name, idx=idx
    )
    reference_column_name = reference_column.value

    return {
        **metadata,
        column_name: {
            **DEFAULT_FIELD_METADATA,  # type: ignore
            **metadata.get(column_name, {}),
            "references": {reference_table_name: reference_column_name},
        },
    }


def _define_column(
    metadata: FieldsMetadata,
    column_definition_group: token_groups.TokenList,
) -> FieldsMetadata:
    idx, column = column_definition_group.token_next_by(t=token_types.Name)
    column_name = column.value

    # "id" is auto-generated by Fauna, so we ignore it in SQL column definitions
    if column_name == "id":
        return metadata

    idx, data_type = column_definition_group.token_next_by(t=token_types.Name, idx=idx)
    _, not_null_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "NOT NULL")
    )
    _, unique_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "UNIQUE")
    )
    _, primary_key_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "PRIMARY KEY")
    )
    _, default_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "DEFAULT")
    )
    _, check_keyword = column_definition_group.token_next_by(
        m=(token_types.Keyword, "CHECK")
    )

    if check_keyword is not None:
        raise exceptions.NotSupportedError("CHECK keyword is not supported.")

    column_metadata: Union[FieldMetadata, Dict[str, str]] = metadata.get(
        column_name, {}
    )
    is_primary_key = primary_key_keyword is not None
    is_not_null = (
        not_null_keyword is not None
        or is_primary_key
        or column_metadata.get("not_null")
        or False
    )
    is_unique = (
        unique_keyword is not None
        or is_primary_key
        or column_metadata.get("unique")
        or False
    )
    default_value = (
        default_keyword
        if default_keyword is None
        else extract_value(default_keyword.value)
    )

    return {
        **metadata,
        column_name: {
            **DEFAULT_FIELD_METADATA,  # type: ignore
            **metadata.get(column_name, {}),  # type: ignore
            "unique": is_unique,
            "not_null": is_not_null,
            "default": default_value,
            "type": DATA_TYPE_MAP[data_type.value],
        },
    }


def _build_fields_metadata(
    metadata: FieldsMetadata,
    column_definition_group: token_groups.TokenList,
) -> FieldsMetadata:
    return (
        _define_primary_key(metadata, column_definition_group)
        or _define_unique_constraint(metadata, column_definition_group)
        or _define_foreign_key_constraint(metadata, column_definition_group)
        or _define_column(metadata, column_definition_group)
    )


def _split_column_identifiers_by_comma(
    column_identifiers: token_groups.IdentifierList,
) -> List[token_groups.TokenList]:
    column_tokens = list(column_identifiers.flatten())
    column_token_list = token_groups.TokenList(column_tokens)
    comma_idxs: List[Optional[int]] = [None]
    comma_idx = -1

    while True:
        if comma_idx is None:
            break

        comma_idx, _ = column_token_list.token_next_by(
            m=(token_types.Punctuation, ","), idx=comma_idx
        )

        comma_idxs.append(comma_idx)

    column_group_ranges = [
        (comma_idxs[comma_idx], comma_idxs[comma_idx + 1])
        for comma_idx in range(0, len(comma_idxs) - 1)
    ]

    return [
        token_groups.TokenList(
            column_tokens[(start if start is None else start + 1) : stop]
        )
        for start, stop in column_group_ranges
    ]


def _extract_column_definitions(
    column_identifiers: token_groups.IdentifierList,
) -> FieldsMetadata:
    # sqlparse doesn't group column info correctly within the Parenthesis,
    # sometimes grouping keywords/identifiers across a comma and breaking them up
    # within the same sub-clause, so we have to do some manual processing
    # to group tokens correctly.
    column_definition_groups = _split_column_identifiers_by_comma(column_identifiers)

    return reduce(_build_fields_metadata, column_definition_groups, {})


def _translate_create_table(
    statement: token_groups.Statement, table_token_idx: int
) -> List[QueryExpression]:
    idx, table_identifier = statement.token_next_by(
        i=token_groups.Identifier, idx=table_token_idx
    )
    table_name = table_identifier.value

    idx, column_identifiers = statement.token_next_by(
        i=token_groups.Parenthesis, idx=idx
    )

    field_metadata = _extract_column_definitions(column_identifiers)
    create_collection = q.create_collection(
        {"name": table_name, "data": {"metadata": {"fields": field_metadata}}}
    )

    index_queries: List[QueryExpression] = []

    index_queries.append(
        q.create_index(
            {"name": f"all_{table_name}", "source": q.collection(table_name)}
        )
    )

    for field_name, field_data in field_metadata.items():
        is_foreign_key = "references" in field_data.keys()
        is_unique = field_data["unique"]
        # Unique columns and foreign keys are such common filter values
        # that it makes sense to automatically create indices for them
        # on table creation.
        is_useful_index = is_unique or is_foreign_key
        if (
            # Fauna can query documents by ID by default, so we don't need
            # an index for it
            field_name == "id"
            or not is_useful_index
        ):
            continue

        index_queries.append(
            q.create_index(
                {
                    "name": f"{table_name}_by_{field_name}",
                    "source": q.collection(table_name),
                    "terms": [{"field": ["data", field_name]}],
                    "unique": is_unique,
                }
            )
        )

    index_queries.append(q.collection(table_name))
    # Unfortunately, expressions in a 'Do' FQL function can not refer to each other
    # (maybe there's some sort of hoisting or pre-run validation check under the hood?),
    # so we have to run the expressions that create the collection
    # and its associated indices separately
    return [create_collection, q.do(index_queries)]


def _translate_create_index(
    statement: token_groups.Statement, idx: int
) -> List[QueryExpression]:
    _, unique = statement.token_next_by(m=(token_types.Keyword, "UNIQUE"), idx=idx)
    idx, _ = statement.token_next_by(m=(token_types.Keyword, "ON"), idx=idx)
    _, index_params = statement.token_next_by(i=token_groups.Function, idx=idx)

    params_idx, table_identifier = index_params.token_next_by(i=token_groups.Identifier)
    table_name = table_identifier.value

    params_idx, column_identifiers = index_params.token_next_by(
        i=token_groups.Parenthesis, idx=params_idx
    )

    index_fields = [
        token.value
        for token in column_identifiers.flatten()
        if token.ttype == token_types.Name
    ]
    index_terms = [{"field": ["data", index_field]} for index_field in index_fields]
    index_name = f"{table_name}_by_{'_and_'.join(sorted(index_fields))}"

    return [
        q.do(
            q.create_index(
                {
                    "name": index_name,
                    "source": q.collection(table_name),
                    "terms": index_terms,
                    "unique": unique,
                }
            ),
            q.collection(table_name),
        )
    ]


def translate_create(statement: token_groups.Statement) -> List[QueryExpression]:
    """Translate a CREATE SQL query into an equivalent FQL query.

    Params:
    -------
    statement: An SQL statement returned by sqlparse.

    Returns:
    --------
    An FQL query expression.
    """
    idx, keyword = statement.token_next_by(
        m=[(token_types.Keyword, "TABLE"), (token_types.Keyword, "INDEX")]
    )

    if keyword.value == "TABLE":
        return _translate_create_table(statement, idx)

    if keyword.value == "INDEX":
        return _translate_create_index(statement, idx)

    raise exceptions.NotSupportedError(
        "Only TABLE and INDEX are supported in CREATE statements."
    )