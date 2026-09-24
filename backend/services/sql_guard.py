"""
SQL safety analysis.

Every statement ABIET runs - AI generated or typed by the user - goes through
``analyze_sql`` first. A statement counts as read-only only if all layers agree:

1. It is a single statement (no ``;``-separated batches).
2. sqlglot parses it as a SELECT / set operation, with no DML, DDL, ``SELECT
   INTO`` or locking clause anywhere in the tree (e.g. data-modifying CTEs).
3. A keyword scan over the statement - with comments, string literals and
   quoted identifiers removed - finds no write/admin keywords. This also covers
   SQL sqlglot cannot parse.
4. No known side-effecting functions are called (``pg_terminate_backend``,
   ``DBMS_LOCK.SLEEP``, ``load_file``, ...).

Read-only connections additionally run inside a transaction that is always
rolled back (and is declared READ ONLY where the database supports it). For
full protection, connect with a database user that only has read permissions.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

logging.getLogger("sqlglot").setLevel(logging.ERROR)

_WRITE_NODES: tuple[type[exp.Expression], ...] = tuple(
    getattr(exp, name)
    for name in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "TruncateTable",
        "Command", "Into", "Copy", "Pragma", "Attach", "Detach", "Execute", "Transaction",
        "Commit", "Rollback", "Set", "Use", "Grant", "Revoke", "LoadData", "Analyze",
    )
    if hasattr(exp, name)
)  # fmt: skip

_STATEMENT_TYPES = {
    "Insert": "insert",
    "Update": "update",
    "Delete": "delete",
    "Merge": "merge",
    "Create": "ddl",
    "Drop": "ddl",
    "Alter": "ddl",
    "TruncateTable": "ddl",
}

# Keywords that never appear in a legitimate read-only query (outside strings/comments).
_ALWAYS_FORBIDDEN = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|UPSERT|DROP|CREATE|ALTER|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE|INTO|"
    r"ATTACH|DETACH|PRAGMA|VACUUM|SHUTDOWN|DBCC|RECONFIGURE|OPENROWSET|OPENDATASOURCE|OPENQUERY|WAITFOR)\b",
    re.IGNORECASE,
)
# Extra keywords checked when sqlglot cannot parse the statement.
_FALLBACK_FORBIDDEN = re.compile(
    r"\b(CALL|COPY|SET|USE|DECLARE|BEGIN|COMMIT|ROLLBACK|SAVEPOINT|LOCK|UNLOCK|KILL|DO|PREPARE|"
    r"OUTFILE|DUMPFILE|LOAD\s+DATA|REPLACE\s+INTO|BACKUP|RESTORE|RENAME)\b",
    re.IGNORECASE,
)
_DANGEROUS_FUNCTIONS = re.compile(
    r"\b(pg_sleep\w*|pg_terminate_backend|pg_cancel_backend|pg_reload_conf|pg_rotate_logfile|pg_promote|"
    r"pg_switch_wal|pg_read_file|pg_read_binary_file|pg_ls_dir|pg_stat_file|pg_file_write|lo_import|lo_export|"
    r"lo_unlink|dblink\w*|set_config|pg_advisory\w*|sleep|benchmark|load_file|get_lock|release_lock|sys_exec|"
    r"sys_eval|load_extension|writefile|readfile|fts3_tokenizer)\s*\(|"
    r"\b(dbms|utl|sys\.dbms)_\w+\s*[.(]",
    re.IGNORECASE,
)
_READ_START = re.compile(r"^\s*(\(\s*)*(SELECT|WITH)\b", re.IGNORECASE)


class SqlRejected(Exception):
    """The statement is not allowed to run."""


@dataclass(frozen=True)
class SqlAnalysis:
    sql: str
    is_read_only: bool
    statement_type: str
    reason: str | None = None


def strip_literals(sql: str, dialect: str) -> str:
    """Replace comments, string literals and quoted identifiers with neutral placeholders."""
    brackets = dialect in ("tsql", "sqlite")
    backslash_escapes = dialect == "mysql"
    out: list[str] = []
    i, n = 0, len(sql)
    while i < n:
        ch = sql[i]
        if sql.startswith("--", i) or (ch == "#" and dialect == "mysql"):
            end = sql.find("\n", i)
            i = n if end == -1 else end
            out.append(" ")
            continue
        if sql.startswith("/*", i):
            end = sql.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
            continue
        if ch == "$" and dialect == "postgres":
            m = re.match(r"\$[A-Za-z_]*\$", sql[i:])
            if m:
                tag = m.group(0)
                end = sql.find(tag, i + len(tag))
                i = n if end == -1 else end + len(tag)
                out.append(" '' ")
                continue
        if ch in "'\"`" or (ch == "[" and brackets):
            close = "]" if ch == "[" else ch
            j = i + 1
            while j < n:
                if backslash_escapes and sql[j] == "\\" and close != "`":
                    j += 2
                    continue
                if sql[j] == close:
                    if j + 1 < n and sql[j + 1] == close:
                        j += 2
                        continue
                    break
                j += 1
            out.append(" '' " if ch == "'" else " _q_ ")
            i = j + 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def clean_sql(sql: str) -> str:
    """Trim whitespace and trailing semicolons."""
    cleaned = sql.strip()
    while cleaned.endswith(";"):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


def _statement_type(node: exp.Expression) -> str:
    return _STATEMENT_TYPES.get(type(node).__name__, "other")


def analyze_sql(sql: str, dialect: str) -> SqlAnalysis:
    """
    Classify a statement. Raises ``SqlRejected`` for input that is never
    allowed (empty, or several statements).
    """
    cleaned = clean_sql(sql or "")
    if not cleaned:
        raise SqlRejected("The SQL statement is empty")

    stripped = strip_literals(cleaned, dialect)
    if ";" in stripped or re.search(r"^\s*GO\s*$", stripped, re.IGNORECASE | re.MULTILINE):
        raise SqlRejected("Only one SQL statement can be run at a time")

    def not_read_only(reason: str, statement_type: str = "other") -> SqlAnalysis:
        return SqlAnalysis(cleaned, False, statement_type, reason)

    try:
        statements = [s for s in sqlglot.parse(cleaned, read=dialect) if s is not None]
    except SqlglotError:
        statements = None

    if statements is not None:
        if len(statements) != 1:
            raise SqlRejected("Only one SQL statement can be run at a time")
        root = statements[0]
        while isinstance(root, (exp.Subquery, exp.Paren)) and root.this is not None:
            root = root.this
        if not isinstance(root, (exp.Select, exp.SetOperation)):
            return not_read_only("Only SELECT queries are allowed on read-only connections", _statement_type(root))
        for node in root.walk():
            if isinstance(node, _WRITE_NODES):
                if isinstance(node, exp.Into):
                    return not_read_only("SELECT ... INTO creates or writes data", "insert")
                operation = type(node).__name__.upper()
                return not_read_only(f"The query contains a {operation} operation", _statement_type(node))
            if isinstance(node, exp.Select) and node.args.get("locks"):
                return not_read_only("Locking reads (FOR UPDATE / FOR SHARE) are not allowed")
    else:
        if not _READ_START.match(stripped):
            return not_read_only("Only SELECT queries are allowed on read-only connections")
        match = _FALLBACK_FORBIDDEN.search(stripped)
        if match:
            return not_read_only(f"'{match.group(0).upper()}' is not allowed in a read-only query")

    match = _ALWAYS_FORBIDDEN.search(stripped)
    if match:
        keyword = match.group(0).upper()
        statement_type = {"INSERT": "insert", "UPDATE": "update", "DELETE": "delete", "MERGE": "merge"}.get(
            keyword, "ddl" if keyword in {"DROP", "CREATE", "ALTER", "TRUNCATE"} else "other"
        )
        return not_read_only(f"'{keyword}' is not allowed in a read-only query", statement_type)
    match = _DANGEROUS_FUNCTIONS.search(stripped)
    if match:
        name = match.group(0).rstrip("(. ").strip()
        return not_read_only(f"The function '{name}' is not allowed")
    return SqlAnalysis(cleaned, True, "select")
