import pandas as pd

from pandasql import load_births, load_meat, sqldf

births = load_births()
meat = load_meat()

print(sqldf("SELECT * FROM meat LIMIT 10;"))
print(sqldf("SELECT date, beef FROM meat LIMIT 10;"))

q = """
      select
        strftime('%Y', date) as year
        , avg(beef)
        , min(beef)
        , max(beef)
      from
        meat
      group by
        year
      limit 10;
    """
print("*" * 80)
print("aggregation")
print("-" * 80)
print(q)
print(sqldf(q))


def pysqldf(q: str) -> pd.DataFrame | None:
    """Add this to your script if you get tired of calling locals()."""
    return sqldf(q, globals())


print("*" * 80)
print("calling from a helper function")
print(
    """def pysqldf(q):
    \"\"\"add this to your script if you get tired of calling locals()\"\"\"
        return sqldf(q, globals())""",
)
print("-" * 80)
print(q)
print(pysqldf(q))

q = """
    SELECT
        m.date
        , m.beef
        , b.births
    FROM
        meat m
    INNER JOIN
        births b
            ON m.date = b.date
    ORDER BY
        m.date
    LIMIT 10;
"""

print("*" * 80)
print("joins")
print("-" * 80)
print(q)
print(pysqldf(q))

q = """
    SELECT
        *
    FROM
        meat
    WHERE
        beef > 2400
    LIMIT 10;
"""
print("*" * 80)
print("where clause")
print("-" * 80)
print(q)
print(pysqldf(q))

q = """
    SELECT
        *
    FROM
        meat
    WHERE
        date IN (
            SELECT date FROM births WHERE births > 350000
        )
    LIMIT 10;
"""
print("*" * 80)
print("subqueries")
print("-" * 80)
print(q)
print(pysqldf(q))
