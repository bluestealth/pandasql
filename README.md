pandasql
========

This is the maintained fork of the archived [yhat/pandasql](https://github.com/yhat/pandasql).
It adds multi-backend SQL support and a more convenient class-based interface.

`pandasql` lets you query `pandas` DataFrames using SQL syntax, similar to `sqldf` in R.
It is aimed at people who prefer SQL for manipulating and cleaning data.

## Installation
```
$ pip install -U pandas_query_sql
```

The import name is still `pandasql`.

`pandas` and SQLAlchemy must stay on the same side of 2.0: use pandas ≤2.1 with
SQLAlchemy 1.4, or pandas ≥2.2 with SQLAlchemy ≥2.0.

## Basics
In addition to the original pandasql `sqldf` function, this fork provides
`PandaSQL`, which new users are encouraged to use.

`PandaSQL` Class
---
`PandaSQL` is convenient when you run multiple queries. It takes 2 arguments:
   - `db_uri`: an optional SQLAlchemy connection string (defaults to in-memory SQLite)
   - `persist`: an optional boolean; if true, loaded tables stay in the database
     between calls (holds the connection open; default `False`)

```python
>>> from pandasql import PandaSQL
>>> pdsql = PandaSQL()  # in-memory SQLite by default
```

A persistent instance holds its database connection open (for PostgreSQL, a
server session) until it is closed or garbage-collected. Close it explicitly
with `close()` or use it as a context manager:

```python
>>> with PandaSQL("postgresql://...", persist=True) as pdsql:
...     result = pdsql("SELECT * FROM df")
```

`sqldf` Function
---
`sqldf` accepts 3 parameters (matching the function signature):
   - `query`: an SQL query string
   - `env`: an optional dict of session/environment variables (defaults to the
     caller's locals and globals)
   - `db_uri`: an optional SQLAlchemy connection string (defaults to in-memory SQLite)


## Querying
SQL syntax is whatever the backend pointed at by `db_uri` expects — SQLite by
default, with PostgreSQL also supported.

Table names in `FROM` / `JOIN` are looked up in the caller's scope (or in the
`env` dict you pass). Only `DataFrame` values are written into the database.
Pass `env=` when you want an explicit mapping instead of auto-detection from
the surrounding scope.

**`persist=True` loads each table name once.** Later calls reuse the table
already in the database, even if the DataFrame with that name has since been
reassigned, modified, or deleted. Use a new `PandaSQL` instance (or
`persist=False`, the default) when you need the current contents of a
DataFrame.

Any `pandas` DataFrames in that environment can be queried as SQL tables:


```
$ python
>>> from pandasql import PandaSQL, load_meat, load_births
>>> meat = load_meat()
>>> births = load_births()
>>> pdsql = PandaSQL()
>>> print(pdsql("SELECT * FROM meat LIMIT 10;").head())
                         date   beef   veal    pork  lamb_and_mutton broilers other_chicken turkey
0  1944-01-01 00:00:00.000000  751.0   85.0  1280.0             89.0     None          None   None
1  1944-02-01 00:00:00.000000  713.0   77.0  1169.0             72.0     None          None   None
2  1944-03-01 00:00:00.000000  741.0   90.0  1128.0             75.0     None          None   None
3  1944-04-01 00:00:00.000000  650.0   89.0   978.0             66.0     None          None   None
4  1944-05-01 00:00:00.000000  681.0  106.0  1029.0             78.0     None          None   None
```

joins and aggregations are also supported
```
>>> q = """SELECT
...         m.date, m.beef, b.births
...      FROM
...         meat m
...      INNER JOIN
...         births b
...            ON m.date = b.date;"""
>>> joined = pdsql(q)
>>> print(joined.head())
                         date    beef  births
0  1975-01-01 00:00:00.000000  2106.0  265775
1  1975-02-01 00:00:00.000000  1845.0  241045
2  1975-03-01 00:00:00.000000  1891.0  268849
3  1975-04-01 00:00:00.000000  1895.0  247455
4  1975-05-01 00:00:00.000000  1849.0  254545

>>> q = """select
...            strftime('%Y', date) as year
...            , SUM(beef) as beef_total
...            FROM
...               meat
...            GROUP BY
...               year;"""
>>> print(pdsql(q).head())
   year  beef_total
0  1944      8801.0
1  1945      9936.0
2  1946      9010.0
3  1947     10096.0
4  1948      8766.0
```
---
## More Info
More information and code samples available in the [examples](https://github.com/bluestealth/pandasql/blob/main/examples/demo.py) folder.
