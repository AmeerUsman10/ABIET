import pytest

from backend.services.sql_guard import SqlRejected, analyze_sql, clean_sql, strip_literals

READ_ONLY = [
    ("tsql", "SELECT TOP 10 * FROM dbo.Customers"),
    ("tsql", "WITH x AS (SELECT 1 a) SELECT * FROM x"),
    ("postgres", "select a::date, b from t where c like 'x%'"),
    ("oracle", "SELECT * FROM t FETCH FIRST 10 ROWS ONLY"),
    ("sqlite", "SELECT 1 UNION SELECT 2"),
    ("tsql", "SELECT [Order Details].* FROM [Order Details]"),
    ("tsql", "SELECT [update] FROM [delete]"),
    ("postgres", "(SELECT 1) UNION ALL (SELECT 2) ORDER BY 1"),
    ("postgres", "SELECT * FROM t WHERE name = 'x; DROP TABLE y'"),
    ("postgres", "SELECT * FROM t -- ; drop table x\n WHERE a = 1"),
    ("postgres", "SELECT 'it''s' AS s, \"Weird;Name\" FROM t"),
    ("postgres", "SELECT deleted_at, updated_by, created FROM t"),
    ("sqlite", "SELECT 1;;"),
    ("mysql", "SELECT 'a\\';DROP TABLE t;--' AS x"),
    ("postgres", "SELECT $$;drop$$ AS x"),
    ("postgres", "SELECT sleepiness FROM survey"),
    ("postgres", "WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n+1 FROM r WHERE n<5) SELECT * FROM r"),
    ("tsql", "SELECT TOP 5 c.name, SUM(o.total) OVER (PARTITION BY c.id) FROM c JOIN o ON o.cid=c.id"),
    ("oracle", "SELECT * FROM (SELECT a FROM t ORDER BY a) WHERE ROWNUM <= 10"),
    ("mysql", "SELECT `order`, COUNT(*) FROM `select` GROUP BY `order`"),
]

NOT_READ_ONLY = [
    ("tsql", "SELECT * INTO backup FROM customers", "insert"),
    ("tsql", "SELECT 1 EXEC xp_cmdshell 'dir'", None),
    ("tsql", "EXEC sp_who", None),
    ("postgres", "WITH d AS (DELETE FROM t RETURNING *) SELECT * FROM d", "delete"),
    ("postgres", "SELECT pg_terminate_backend(123)", None),
    ("postgres", "SELECT * FROM t FOR UPDATE", None),
    ("postgres", "COPY t TO '/tmp/x'", None),
    ("mysql", "SELECT * FROM t INTO OUTFILE '/tmp/x'", None),
    ("oracle", "SELECT DBMS_LOCK.SLEEP(10) FROM dual", None),
    ("sqlite", "PRAGMA table_info(x)", None),
    ("sqlite", "ATTACH DATABASE 'x' AS y", None),
    ("tsql", "UPDATE t SET a=1", "update"),
    ("tsql", "delete from t", "delete"),
    ("postgres", "INSERT INTO t VALUES (1)", "insert"),
    ("postgres", "DROP TABLE t", "ddl"),
    ("postgres", "EXPLAIN ANALYZE DELETE FROM t", None),
    ("mysql", "SELECT SLEEP(5)", None),
    ("tsql", "SELECT * FROM OPENROWSET('SQLNCLI','x','select 1')", None),
    ("postgres", "SELECT dblink_exec('x', 'drop table t')", None),
    ("sqlite", "SELECT load_extension('evil')", None),
]


@pytest.mark.parametrize(("dialect", "sql"), READ_ONLY)
def test_read_only_statements_are_allowed(dialect, sql):
    analysis = analyze_sql(sql, dialect)
    assert analysis.is_read_only, analysis.reason
    assert analysis.statement_type == "select"


@pytest.mark.parametrize(("dialect", "sql", "statement_type"), NOT_READ_ONLY)
def test_writes_and_side_effects_are_flagged(dialect, sql, statement_type):
    analysis = analyze_sql(sql, dialect)
    assert not analysis.is_read_only
    assert analysis.reason
    if statement_type:
        assert analysis.statement_type == statement_type


@pytest.mark.parametrize(
    ("dialect", "sql"),
    [
        ("postgres", "SELECT 1; DROP TABLE x"),
        ("tsql", "SELECT 1\nGO\nDROP TABLE x"),
        ("sqlite", "   "),
        ("sqlite", ";"),
        ("postgres", "UPDATE a SET x = 1; UPDATE b SET y = 2"),
    ],
)
def test_empty_and_multiple_statements_are_rejected(dialect, sql):
    with pytest.raises(SqlRejected):
        analyze_sql(sql, dialect)


def test_trailing_semicolons_are_stripped():
    assert clean_sql("  SELECT 1 ;; ") == "SELECT 1"
    assert analyze_sql("SELECT 1;", "postgres").sql == "SELECT 1"


def test_strip_literals_removes_strings_comments_and_quoted_identifiers():
    stripped = strip_literals("SELECT 'drop' /* delete */ AS \"insert\" -- update\nFROM [exec]", "tsql")
    for word in ("drop", "delete", "insert", "update", "exec"):
        assert word not in stripped.lower()
    assert "SELECT" in stripped and "FROM" in stripped


def test_brackets_are_not_identifiers_in_postgres():
    # Postgres array subscripts must not hide keywords.
    analysis = analyze_sql("SELECT a[1] FROM t WHERE b = 1", "postgres")
    assert analysis.is_read_only
