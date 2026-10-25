import pytest

from pandasql.sqldf import _extract_table_names_regex, extract_table_names, get_outer_frame_variables


def test_get_vars() -> None:
    var_a = 123
    variable = {"a": "b", "c": "d"}
    assert get_outer_frame_variables()["var_a"] == var_a
    assert get_outer_frame_variables()["variable"] == variable


def test_get_vars_from_nested_helper() -> None:
    # a helper that wraps the call sees its own scope, not its caller's: this is the
    # documented `def pysqldf(q): return sqldf(q, globals())` pattern
    def helper() -> dict[str, object]:
        helper_local = 1
        assert helper_local
        return get_outer_frame_variables()

    caller_local = 2
    assert caller_local
    variables = helper()
    assert "helper_local" in variables
    assert "caller_local" not in variables


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("", set()),
        ("SELECT * FROM dbtbl LIMIT 10", {"dbtbl"}),
        ("SELECT * from dbtbl LIMIT 10", {"dbtbl"}),
        (
            "SELECT * FROM dbtbl JOIN table_2 USING (a) LEFT JOIN mytable USING (b)",
            {"dbtbl", "table_2", "mytable"},
        ),
        (
            "SELECT * FROM dbtbl, table_2, mytable JOIN another USING (a)",
            {"dbtbl", "table_2", "mytable", "another"},
        ),
        ("SELECT * FROM dbtbl, table_2 JOIN dbtbl USING (a)", {"dbtbl", "table_2"}),
        pytest.param(
            "SELECT * FROM dbtbl WHERE col = 'Go and join us!'",
            {"dbtbl"},
        ),
        (
            "SELECT * FROM course_df WHERE coursecode IN ( SELECT DISTINCT coursecode FROM program_df )",
            {"course_df", "program_df"},
        ),
        (
            "SELECT * FROM course_df, (SELECT coursecode FROM program_df) ssel",
            {"course_df", "program_df"},
        ),
        # literals and comments must not be mistaken for table references
        ("SELECT * FROM dbtbl WHERE col = 'it''s FROM nowhere'", {"dbtbl"}),
        ("SELECT * FROM dbtbl -- FROM hidden", {"dbtbl"}),
        ("SELECT * FROM dbtbl /* JOIN ghost\n JOIN other */ LIMIT 1", {"dbtbl"}),
        ('SELECT * FROM dbtbl WHERE col = "JOIN"', {"dbtbl"}),
        # quoted identifiers are real table names
        ('SELECT * FROM "Quoted Table"', {"Quoted Table"}),
        ("SELECT * FROM `dbtbl`", {"dbtbl"}),
        # CTE aliases are not tables, however deeply nested
        ("WITH t AS (SELECT * FROM meat) SELECT * FROM t", {"meat"}),
        ("WITH t AS (WITH u AS (SELECT * FROM meat) SELECT * FROM u) SELECT * FROM t", {"meat"}),
        ("WITH RECURSIVE c(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM c WHERE n < 5) SELECT * FROM c, df", {"df"}),
        # schema-qualified names cannot be dataframes
        ("SELECT * FROM information_schema.tables", set()),
        ("SELECT * FROM main.dbtbl JOIN other", {"other"}),
        # DML targets are tables; the object created by CREATE TABLE is not
        ("UPDATE meat SET beef = 1", {"meat"}),
        ("DELETE FROM meat WHERE beef = 1", {"meat"}),
        ("INSERT INTO dest SELECT * FROM meat", {"dest", "meat"}),
        ("CREATE TABLE tbl (col INTEGER)", set()),
        ("CREATE TABLE tbl AS SELECT * FROM meat", {"meat"}),
        # multiple statements and malformed input
        ("SELECT * FROM a; SELECT * FROM b;", {"a", "b"}),
        ("SELEC * FORM df", set()),
        ("SELECT * FROM", set()),
    ],
)
def test_extract_table_names(query: str, expected: set[str]) -> None:
    assert extract_table_names(query) == expected


@pytest.mark.parametrize(
    ("query", "engine_name", "expected"),
    [
        ("SELECT * FROM df WHERE a ~ 'x'", "postgresql", {"df"}),
        ("SELECT * FROM df WHERE a GLOB 'x*'", "sqlite", {"df"}),
        ("SELECT * FROM df WHERE a ILIKE '%x%'", "postgresql", {"df"}),
    ],
)
def test_extract_table_names_dialect(query: str, engine_name: str, expected: set[str]) -> None:
    assert extract_table_names(query, engine_name) == expected


@pytest.mark.parametrize(
    "query",
    [
        # postgres syntax sqlglot does not parse; the regex fallback must still find the table
        "SELECT a FROM df ORDER BY a USING < NULLS FIRST",
        "SELECT * FROM df WHERE a |>> b",
    ],
)
def test_extract_table_names_falls_back_to_regex(query: str) -> None:
    assert extract_table_names(query, "postgresql") == {"df"}
    assert extract_table_names(query, "postgresql") == _extract_table_names_regex(query)


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        # the fallback is intentionally the pre-parser behaviour, limits included
        ("SELECT * FROM dbtbl WHERE col = 'Go and join us!'", {"dbtbl", "us"}),
        ('SELECT * FROM "Quoted Table"', set()),
        ("SELECT * FROM information_schema.tables", {"information_schema"}),
        ("WITH t AS (SELECT * FROM meat) SELECT * FROM t", {"meat", "t"}),
        ("SELEC * FORM df", set()),
    ],
)
def test_extract_table_names_regex(query: str, expected: set[str]) -> None:
    assert _extract_table_names_regex(query) == expected
