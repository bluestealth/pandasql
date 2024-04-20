import importlib.metadata
import string
from typing import Any, Dict

import packaging.version
import pandas as pd
import pandas.testing as pdtest
import pytest

from pandasql import PandaSQL, PandaSQLException, load_meat, sqldf

PANDAS_MAJOR_VERSION = packaging.version.Version(
    importlib.metadata.version("pandas")
).major


@pytest.fixture()
def db_uris() -> Dict[str, str]:
    return {
        "sqlite": "sqlite:///:memory:",
        "postgres": "postgresql://postgres@localhost/",
    }


@pytest.fixture(params=["sqlite", "postgres"])
def db_flavor(request: pytest.FixtureRequest) -> Any:
    return request.param


@pytest.fixture()
def db_uri(db_uris: Dict[str, str], db_flavor: str) -> str:
    return db_uris[db_flavor]


@pytest.fixture(params=[False, True])
def pdsql(db_uri: str, request: pytest.FixtureRequest) -> PandaSQL:
    return PandaSQL(db_uri, persist=request.param)


def test_select_legacy(db_uri: str) -> None:
    df = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "l2": list(string.ascii_letters),
        }
    )
    result = sqldf("SELECT * FROM df LIMIT 10", db_uri=db_uri)

    assert result is not None
    assert len(result) == 10
    pdtest.assert_frame_equal(df.head(10), result)


def test_select(pdsql: PandaSQL) -> None:
    df = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "l2": list(string.ascii_letters),
        }
    )
    result = pdsql("SELECT * FROM df LIMIT 10")

    assert result is not None
    assert len(result) == 10
    pdtest.assert_frame_equal(df.head(10), result)


def test_join(pdsql: PandaSQL) -> None:
    df = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "l2": list(string.ascii_letters),
        }
    )

    df2 = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "letter": list(string.ascii_letters),
        }
    )

    result = pdsql(
        "SELECT a.*, b.letter FROM df a INNER JOIN df2 b ON a.l2 = b.letter LIMIT 20"
    )

    assert result is not None
    assert len(result) == 20
    pdtest.assert_frame_equal(
        df[["letter_pos", "l2"]].head(20), result[["letter_pos", "l2"]]
    )
    pdtest.assert_frame_equal(df2[["letter"]].head(20), result[["letter"]])


def test_query_with_spacing(pdsql: PandaSQL) -> None:
    df = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "l2": list(string.ascii_letters),
        }
    )
    assert df is not None

    df2 = pd.DataFrame(
        {
            "letter_pos": range(len(string.ascii_letters)),
            "letter": list(string.ascii_letters),
        }
    )
    assert df2 is not None

    expected = pdsql(
        "SELECT a.*, b.letter FROM df a INNER JOIN df2 b ON a.l2 = b.letter LIMIT 20"
    )
    assert expected is not None

    q = """
        SELECT
        a.*
    , b.letter
    FROM
        df a
    INNER JOIN
        df2 b
    on a.l2 = b.letter
    LIMIT 20
    """
    result = pdsql(q)
    assert result is not None
    assert len(result) == 20
    pdtest.assert_frame_equal(expected, result)


def test_subquery(pdsql: PandaSQL) -> None:
    kermit = pd.DataFrame({"x": range(10)})
    result = pdsql("SELECT * FROM (SELECT * FROM kermit) tbl LIMIT 2")
    assert result is not None
    pdtest.assert_frame_equal(kermit.head(2), result)
    assert len(result) == 2


def test_in(pdsql: PandaSQL) -> None:
    course_data = {
        "coursecode": ["TM351", "TU100", "M269"],
        "points": [30, 60, 30],
        "level": ["3", "1", "2"],
    }
    course_df = pd.DataFrame(course_data)
    assert not course_df.empty

    result = pdsql("SELECT * FROM course_df WHERE coursecode IN ( 'TM351', 'TU100' )")
    assert result is not None
    assert len(result) == 2


def test_in_with_subquery(pdsql: PandaSQL) -> None:
    program_data = {
        "coursecode": [
            "TM351",
            "TM351",
            "TM351",
            "TU100",
            "TU100",
            "TU100",
            "M269",
            "M269",
            "M269",
        ],
        "programCode": ["AB1", "AB2", "AB3", "AB1", "AB3", "AB4", "AB3", "AB4", "AB5"],
    }
    program_df = pd.DataFrame(program_data)
    assert not program_df.empty

    courseData = {
        "coursecode": ["TM351", "TU100", "M269"],
        "points": [30, 60, 30],
        "level": ["3", "1", "2"],
    }
    course_df = pd.DataFrame(courseData)
    assert not course_df.empty

    result = pdsql(
        "SELECT * FROM course_df WHERE coursecode IN ( SELECT DISTINCT coursecode FROM program_df )"
    )
    assert result is not None
    assert len(result) == 3


def test_datetime_query(pdsql: PandaSQL, db_flavor: str) -> None:
    meat = load_meat()
    expected = meat[meat["date"] >= "2012-01-01"].reset_index(drop=True)
    result = pdsql("SELECT * FROM meat WHERE date >= '2012-01-01'")
    assert result is not None

    if db_flavor == "sqlite":
        # sqlite uses strings instead of datetimes
        pdtest.assert_frame_equal(
            expected.drop(labels="date", axis="columns"),
            result.drop(labels="date", axis="columns"),
        )
    else:
        pdtest.assert_frame_equal(expected, result)


def test_returning_single(pdsql: PandaSQL) -> None:
    meat = load_meat()
    result = pdsql("SELECT beef FROM meat LIMIT 10")
    assert result is not None
    assert len(result) == 10
    pdtest.assert_frame_equal(meat[["beef"]].head(10), result)


def test_name_index(pdsql: PandaSQL) -> None:
    df = pd.DataFrame(
        {
            "index": range(len(string.ascii_letters)),
            "level_0": range(len(string.ascii_letters)),
            "level_1": range(len(string.ascii_letters)),
            "letter": list(string.ascii_letters),
        }
    )
    result = pdsql("SELECT * FROM df")
    assert result is not None
    pdtest.assert_frame_equal(df, result)


def test_nonexistent_table(pdsql: PandaSQL) -> None:
    with pytest.raises(PandaSQLException):
        pdsql("SELECT * FROM nosuchtablereally")


def test_system_tables(pdsql: PandaSQL, db_flavor: str) -> None:
    if db_flavor == "sqlite":
        # sqlite doesn't have information_schema
        result = pdsql("SELECT * FROM sqlite_master")
    else:
        result = pdsql("SELECT * FROM information_schema.tables")
    assert result is not None
    assert len(result.columns) > 1


@pytest.mark.parametrize(
    "db_flavor", ["postgres"]
)  # sqlite doesn't support tables with no columns
def test_no_columns(pdsql: PandaSQL) -> None:
    df = pd.DataFrame()
    result = pdsql("SELECT * FROM df")
    assert result is not None
    assert df.empty and result.empty
    pdtest.assert_frame_equal(df, result, check_column_type=(PANDAS_MAJOR_VERSION < 2))


def test_empty(pdsql: PandaSQL) -> None:
    df = pd.DataFrame({"x": []})
    result = pdsql("SELECT * FROM df")
    assert result is not None
    assert result.empty
    pdtest.assert_index_equal(df.columns, result.columns)


def test_noleak_legacy(db_uri: str) -> None:
    df = pd.DataFrame({"x": [1]})
    result = sqldf("SELECT * FROM df", db_uri=db_uri)
    assert result is not None
    pdtest.assert_frame_equal(df, result)
    del df
    with pytest.raises(PandaSQLException):
        result = sqldf("SELECT * FROM df", db_uri=db_uri)


@pytest.mark.parametrize("pdsql", [False], indirect=True)
def test_noleak_class(pdsql: PandaSQL) -> None:
    df = pd.DataFrame({"x": [1]})
    result = pdsql("SELECT * FROM df")
    assert result is not None
    pdtest.assert_frame_equal(df, result)
    del df
    with pytest.raises(PandaSQLException):
        result = pdsql("SELECT * FROM df")


def test_same_query_noerr(pdsql: PandaSQL) -> None:
    df = pd.DataFrame({"x": [1]})
    result1 = pdsql("SELECT * FROM df")
    assert result1 is not None
    pdtest.assert_frame_equal(df, result1)
    result2 = pdsql("SELECT * FROM df")
    assert result2 is not None
    pdtest.assert_frame_equal(result1, result2)


@pytest.mark.parametrize("pdsql", [True], indirect=True)
def test_persistent(pdsql: PandaSQL) -> None:
    df = pd.DataFrame({"x": [1]})
    result1 = pdsql("SELECT * FROM df")
    assert result1 is not None
    pdtest.assert_frame_equal(df, result1)

    del df
    result2 = pdsql("SELECT * FROM df")
    assert result2 is not None
    pdtest.assert_frame_equal(result1, result2)

    df = pd.DataFrame({"x": [1, 2]})  # will not have any effect
    assert not df.empty
    result3 = pdsql("SELECT * FROM df")
    assert result3 is not None
    pdtest.assert_frame_equal(result1, result3)

    df1 = pd.DataFrame({"x": [1, 2, 3]})
    result4 = pdsql("SELECT * FROM df1")
    assert result4 is not None
    pdtest.assert_frame_equal(df1, result4)


def test_noreturn_query(pdsql: PandaSQL) -> None:
    assert pdsql("CREATE TABLE tbl (col INTEGER)") is None


@pytest.mark.parametrize("pdsql", [False], indirect=True)
def test_no_sideeffect_leak(pdsql: PandaSQL) -> None:
    pdsql("CREATE TABLE tbl (col INTEGER)")
    with pytest.raises(PandaSQLException):
        result = pdsql("SELECT * FROM tbl")
        assert result is not None


@pytest.mark.parametrize("pdsql", [True], indirect=True)
def test_sideeffect_persist(pdsql: PandaSQL) -> None:
    pdsql("CREATE TABLE tbl (col INTEGER)")
    result = pdsql("SELECT * FROM tbl")
    assert result is not None
    assert list(result.columns) == ["col"]
