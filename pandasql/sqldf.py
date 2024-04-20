import importlib.metadata
import inspect
import re
import sqlite3
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional, Set, Union
from warnings import catch_warnings, filterwarnings

import packaging.version
from pandas import DataFrame
from pandas.io.sql import read_sql_query
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.event import listen
from sqlalchemy.pool.base import _ConnectionRecord
from sqlalchemy.exc import DatabaseError, ResourceClosedError
from sqlalchemy.pool import NullPool

__all__ = ["PandaSQL", "PandaSQLException", "sqldf"]

SQLALCHEMY_MAJOR_VERSION = packaging.version.Version(
    importlib.metadata.version("sqlalchemy")
).major


class PandaSQLException(Exception):
    pass


class PandaSQL:
    def __init__(self, db_uri: Optional[str], persist: bool = False) -> None:
        """
        Initialize with a specific database.

        :param db_uri: SQLAlchemy-compatible database URI.
        :param persist: keep tables in database between different calls on the same object of this class.
        """
        if not db_uri:
            db_uri = "sqlite:///:memory:"

        self.engine = create_engine(url=db_uri, poolclass=NullPool)

        if self.engine.name == "sqlite":
            listen(target=self.engine, identifier="connect", fn=self._set_text_factory)
        elif self.engine.name == "postgresql":
            pass
        else:
            raise PandaSQLException(
                "Currently only sqlite and postgresql are supported."
            )

        self.persist = persist
        self.loaded_tables: Set[str] = set()
        if self.persist:
            self._conn = self.engine.connect()
            self._init_connection(self._conn)

    def __call__(
        self, query: str, env: Optional[Dict[str, Any]] = None
    ) -> Optional[DataFrame]:
        """
        Execute the SQL query.
        Automatically creates tables mentioned in the query from dataframes before executing.

        :param query: SQL query string, which can reference pandas dataframes as SQL tables.
        :param env: Variables environment - a dict mapping table names to pandas dataframes.
        If not specified use local and global variables of the caller.
        :return: Pandas dataframe with the result of the SQL query.
        """
        if env is None:
            env = get_outer_frame_variables()

        with self.conn as conn:
            for table_name in extract_table_names(query):
                if table_name not in env:
                    # don't raise error because the table may be already in the database
                    continue
                if self.persist and table_name in self.loaded_tables:
                    # table was loaded before using the same instance, don't do it again
                    continue
                self.loaded_tables.add(table_name)
                write_table(df=env[table_name], tablename=table_name, conn=conn)

            try:
                result = read_sql_query(sql=query, con=conn)
            except DatabaseError as ex:
                raise PandaSQLException(ex)
            except ResourceClosedError:
                # query returns nothing
                result = None

        return result

    @property
    @contextmanager
    def conn(self) -> Iterator[Connection]:
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
                from sqlalchemy import text

                conn.execute(statement=text("set search_path to pg_temp"))
            else:
                conn.execute(statement="set search_path to pg_temp")

    def _set_text_factory(
        self, dbapi_conn: sqlite3.Connection, _: _ConnectionRecord
    ) -> None:
        dbapi_conn.text_factory = str


def get_outer_frame_variables() -> Dict[str, Any]:
    """Get a dict of local and global variables of the first outer frame from another file."""
    frame = inspect.currentframe()
    variables: Dict[str, Any] = {}

    if not frame:
        return variables

    cur_filename = inspect.getframeinfo(frame).filename
    outer_frame = next(
        f
        for f in inspect.getouterframes(inspect.currentframe())
        if f.filename != cur_filename
    )
    variables.update(outer_frame.frame.f_globals)
    variables.update(outer_frame.frame.f_locals)
    return variables


def extract_table_names(query: str) -> Set[str]:
    """Extract table names from an SQL query."""
    # a good old fashioned regex. turns out this worked better than actually parsing the code
    tables_blocks = re.findall(
        r"(?:FROM|JOIN)\s+(\w+(?:\s*,\s*\w+)*)", query, re.IGNORECASE
    )
    return {tbl for block in tables_blocks for tbl in re.findall(r"\w+", block)}


def write_table(
    df: DataFrame, tablename: str, conn: Union[Engine, Connection, sqlite3.Connection]
) -> None:
    """Write a dataframe to the database."""
    with catch_warnings():
        filterwarnings(
            "ignore",
            message=f"The provided table name '{tablename}' is not found exactly as such in the database",
        )
        df.to_sql(
            name=tablename,
            con=conn,
            index=not any(name is None for name in df.index.names),  # type: ignore
        )  # load index into db if all levels are named


def sqldf(
    query: str, env: Optional[Dict[str, Any]] = None, db_uri: Optional[str] = None
) -> Optional[DataFrame]:
    """
    Query pandas data frames using sql syntax
    This function is meant for backward compatibility only. New users are encouraged to use the PandaSQL class.

    Parameters
    ----------
    query: string
        a sql query using DataFrames as tables
    env: locals() or globals()
        variable environment; locals() or globals() in your function
        allows sqldf to access the variables in your python environment
    db_uri: string
        SQLAlchemy-compatible database URI

    Returns
    -------
    result: DataFrame
        returns a DataFrame with your query's result

    Examples
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
