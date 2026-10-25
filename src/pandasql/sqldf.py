"""SQL DataFrame File."""

import importlib.metadata
import inspect
import re
import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any
from warnings import catch_warnings, filterwarnings

import packaging.version
import sqlglot
from pandas import DataFrame
from pandas.errors import DatabaseError as PandasDatabaseError
from pandas.io.sql import read_sql_query
from sqlalchemy import create_engine  # pyright: ignore[reportUnknownVariableType]
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.event import listen  # pyright: ignore[reportUnknownVariableType]
from sqlalchemy.exc import DatabaseError as SQLAlchemyDatabaseError
from sqlalchemy.exc import ResourceClosedError, SQLAlchemyError
from sqlalchemy.pool import NullPool
from sqlalchemy.pool.base import (
    _ConnectionRecord,  # pyright: ignore[reportPrivateUsage]
)
from sqlglot import exp
from sqlglot.errors import ParseError

__all__ = ["PandaSQL", "PandaSQLException", "sqldf"]

SQLALCHEMY_MAJOR_VERSION = packaging.version.Version(
    importlib.metadata.version("sqlalchemy"),
).major

ENGINE_TO_DIALECT = {"sqlite": "sqlite", "postgresql": "postgres"}


class PandaSQLException(Exception):
    """Exception Class for PandaSQL."""


class PandaSQL:
    """Class for using SQL database to query pandas DataFrames.

    Attributes:
        engine: sqlalchemy database engine
        persist: boolean to determine if tables stay loaded between function calls
        loaded_tables: set of currently loaded table names
    """

    def __init__(self, db_uri: str | None = None, persist: bool = False) -> None:
        """Initialize with a specific database.

        :param db_uri: SQLAlchemy-compatible database URI.
        :param persist: keep tables in database between different calls on the same object of this class.
        """
        if not db_uri:
            db_uri = "sqlite:///:memory:"

        self.engine: Engine = create_engine(url=db_uri, poolclass=NullPool)

        if self.engine.name == "sqlite":
            listen(target=self.engine, identifier="connect", fn=PandaSQL._set_text_factory)
        elif self.engine.name == "postgresql":
            pass
        else:
            raise PandaSQLException(
                "Currently only sqlite and postgresql are supported.",
            )

        self.persist = persist
        self.loaded_tables: set[str] = set()
        if self.persist:
            self._conn = self.engine.connect()
            self._init_connection(self._conn)

    def __call__(
        self,
        query: str,
        env: dict[str, Any] | None = None,
    ) -> DataFrame | None:
        """Execute the SQL query.

        Automatically creates tables mentioned in the query from dataframes before executing.

        :param query: SQL query string, which can reference pandas dataframes as SQL tables.
        :param env: Variables environment - a dict mapping table names to pandas dataframes.
        If not specified use local and global variables of the caller.
        :return: Pandas dataframe with the result of the SQL query.
        """
        if env is None:
            env = get_outer_frame_variables()

        with self.conn as conn:
            for table_name in extract_table_names(query, self.engine.name):
                df = env.get(table_name)
                if not isinstance(df, DataFrame):
                    continue
                if self.persist and table_name in self.loaded_tables:
                    continue
                try:
                    write_table(df=df, tablename=table_name, conn=conn)
                except (ValueError, SQLAlchemyError, PandasDatabaseError) as ex:
                    raise PandaSQLException(ex) from ex
                self.loaded_tables.add(table_name)

            try:
                result = read_sql_query(sql=query, con=conn)
            except ResourceClosedError:
                # query returns nothing
                result = None
            except (SQLAlchemyDatabaseError, PandasDatabaseError) as ex:
                raise PandaSQLException(ex) from ex

        return result

    @property
    @contextmanager
    def conn(self) -> Generator[Connection]:
        """Context Manager for database connection."""
        if self.persist:
            # the connection is created in __init__, so just return it
            yield self._conn
            # no cleanup needed
        else:
            # create the connection
            conn = self.engine.connect()
            self._init_connection(conn)
            try:
                yield conn
            finally:
                # cleanup - close connection on exit
                conn.close()

    def _init_connection(self, conn: Connection) -> None:
        if self.engine.name == "postgresql":
            if SQLALCHEMY_MAJOR_VERSION >= 2:
                from sqlalchemy import text  # noqa: PLC0415

                conn.execute(  # pyright: ignore[reportUnknownMemberType]
                    statement=text("set search_path to pg_temp"),
                )
            else:
                conn.execute(  # ty: ignore[no-matching-overload]
                    statement="set search_path to pg_temp",
                )

    @staticmethod
    def _set_text_factory(
        dbapi_conn: sqlite3.Connection,
        _: _ConnectionRecord,
    ) -> None:
        dbapi_conn.text_factory = str


def get_outer_frame_variables() -> dict[str, Any]:
    """Get a dict of local and global variables of the first outer frame from another file."""
    frame = inspect.currentframe()
    variables: dict[str, Any] = {}

    if not frame:
        return variables

    cur_filename = inspect.getframeinfo(frame).filename
    outer_frame = next(f for f in inspect.getouterframes(inspect.currentframe()) if f.filename != cur_filename)
    variables.update(outer_frame.frame.f_globals)
    variables.update(outer_frame.frame.f_locals)
    return variables


def _extract_table_names_regex(query: str) -> set[str]:
    """Extract table names from an SQL query regex fallaback."""
    tables_blocks = re.findall(
        r"(?:FROM|JOIN)\s+(\w+(?:\s*,\s*\w+)*)",
        query,
        re.IGNORECASE,
    )
    return {tbl for block in tables_blocks for tbl in re.findall(r"\w+", block)}


def extract_table_names(query: str, engine_name: str = "sqlite") -> set[str]:
    """Extract table names from an SQL query."""
    dialect = ENGINE_TO_DIALECT.get(engine_name)
    try:
        statements = sqlglot.parse(query, read=dialect)
    except ParseError:
        return _extract_table_names_regex(query)
    names: set[str] = set()
    for stmt in statements:
        if stmt is None:
            continue
        ctes = {cte.alias_or_name for cte in stmt.find_all(exp.CTE)}
        for table in stmt.find_all(exp.Table):
            if table.db or table.catalog or isinstance(table.parent, exp.Create):
                continue
            if table.name and table.name not in ctes:
                names.add(table.name)
    return names


def write_table(
    df: DataFrame,
    tablename: str,
    conn: Engine | Connection | sqlite3.Connection,
) -> None:
    """Write Pandas DataFrame to SQL Table.

    Parameters:
    df: pandas.DataFrame
        dataframe to serialize
    tablename: string
        name of sql table to write
    conn: sqlite or sqlalchemy connector
        connection to sql database
    """
    with catch_warnings():
        filterwarnings(
            "ignore",
            message=f"The provided table name '{tablename}' is not found exactly as such in the database",
        )
        df.to_sql(
            name=tablename,
            con=conn,
            index=not any(
                name is None  # pyright: ignore[reportUnnecessaryComparison]
                for name in df.index.names  # pyright: ignore[reportUnknownMemberType]
            ),
        )  # load index into db if all levels are named


def sqldf(
    query: str,
    env: dict[str, Any] | None = None,
    db_uri: str | None = None,
) -> DataFrame | None:
    """Query pandas data frames using sql syntax.

    This function is meant for backward compatibility only. New users are encouraged to use the PandaSQL class.

    Parameters:
    ----------
    query: string
        a sql query using DataFrames as tables
    env: locals() or globals()
        variable environment; locals() or globals() in your function
        allows sqldf to access the variables in your python environment
    db_uri: string
        SQLAlchemy-compatible database URI

    Returns:
    -------
    result: DataFrame
        returns a DataFrame with your query's result

    Examples:
    --------
    >>> import pandas as pd
    >>> df = pd.DataFrame({
        "x": range(100),
        "y": range(100)
    })
    >>> from pandasql import sqldf
    >>> sqldf("select * from df;", globals())
    >>> sqldf("select * from df;", locals())
    >>> sqldf("select avg(x) from df;", locals())
    """
    return PandaSQL(db_uri=db_uri)(query, env)
