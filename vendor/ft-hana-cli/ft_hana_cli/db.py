"""HANA connection wrapper. Read-only by contract; never exposes execute()."""

import re
from contextlib import contextmanager
from typing import Iterator, List, Optional, Sequence, Tuple

from hdbcli import dbapi

# SAP B1 identifiers we need to support: OITM, RDR1, T0, @MLMM, @SRCG,
# "Tableau Export View With Items", "2025_commission_program", etc.
_SAFE_IDENTIFIER = re.compile(r"^[A-Za-z0-9 _@&\-/.]+$")


def _safe_identifier(name: str) -> str:
    if not _SAFE_IDENTIFIER.fullmatch(name):
        raise ValueError(f"unsafe identifier: {name!r}")
    return name


Rows = Tuple[List[str], List[list]]


class HanaDB:
    """Thin wrapper around an hdbcli connection. Read-only by design."""

    def __init__(self, conn, schema: str):
        self._conn = conn
        self.schema = schema

    def query(self, sql: str, params: Optional[Sequence] = None) -> Rows:
        """Execute SQL and return (column_names, rows). No DataFrame dependency."""
        cursor = self._conn.cursor()
        try:
            if params is None:
                cursor.execute(sql)
            else:
                cursor.execute(sql, params)
            if cursor.description is None:
                return [], []
            cols = [d[0] for d in cursor.description]
            rows = [list(r) for r in cursor.fetchall()]
            return cols, rows
        finally:
            cursor.close()

    # -- introspection (parameterized; never f-string into SQL) ---------------

    def list_tables(self, pattern: str = "%") -> Rows:
        sql = """
            SELECT 'TABLE' AS "Type", "TABLE_NAME" AS "Name"
            FROM "SYS"."TABLES"
            WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" LIKE ?
            UNION ALL
            SELECT 'VIEW', "VIEW_NAME"
            FROM "SYS"."VIEWS"
            WHERE "SCHEMA_NAME" = ? AND "VIEW_NAME" LIKE ?
            ORDER BY "Name"
        """
        return self.query(sql, (self.schema, pattern, self.schema, pattern))

    def columns_of(self, table: str) -> Rows:
        # Try TABLE_COLUMNS first, then VIEW_COLUMNS — SAP B1 has both.
        sql_t = """
            SELECT "COLUMN_NAME", "DATA_TYPE_NAME", "LENGTH", "IS_NULLABLE"
            FROM "SYS"."TABLE_COLUMNS"
            WHERE "SCHEMA_NAME" = ? AND "TABLE_NAME" = ?
            ORDER BY "POSITION"
        """
        cols, rows = self.query(sql_t, (self.schema, table))
        if not rows:
            sql_v = """
                SELECT "COLUMN_NAME", "DATA_TYPE_NAME", "LENGTH", "IS_NULLABLE"
                FROM "SYS"."VIEW_COLUMNS"
                WHERE "SCHEMA_NAME" = ? AND "VIEW_NAME" = ?
                ORDER BY "POSITION"
            """
            cols, rows = self.query(sql_v, (self.schema, table))
        return cols, rows

    def search_columns(self, name_pattern: str) -> Rows:
        sql = """
            SELECT "TABLE_NAME" AS "Object", 'TABLE' AS "Kind",
                   "COLUMN_NAME", "DATA_TYPE_NAME"
            FROM "SYS"."TABLE_COLUMNS"
            WHERE "SCHEMA_NAME" = ? AND "COLUMN_NAME" LIKE ?
            UNION ALL
            SELECT "VIEW_NAME", 'VIEW',
                   "COLUMN_NAME", "DATA_TYPE_NAME"
            FROM "SYS"."VIEW_COLUMNS"
            WHERE "SCHEMA_NAME" = ? AND "COLUMN_NAME" LIKE ?
            ORDER BY "Object", "COLUMN_NAME"
        """
        return self.query(
            sql, (self.schema, name_pattern, self.schema, name_pattern)
        )

    def sample_rows(self, table: str, n: int = 5) -> Rows:
        # HANA does not allow `?` placeholders for identifiers or TOP-N.
        # Use a strict identifier check + an int cast for n.
        safe = _safe_identifier(table)
        n_int = int(n)
        sql = f'SELECT TOP {n_int} * FROM "{self.schema}"."{safe}"'
        return self.query(sql)

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


def connect(
    host: str,
    port: int,
    user: str,
    password: str,
    schema: str,
    encrypt: bool = False,
    validate_cert: bool = False,
    timeout_ms: int = 10_000,
) -> HanaDB:
    """Open a HANA connection. Defaults match Frama-Tech on-prem at 30015."""
    kwargs = dict(
        address=host,
        port=int(port),
        user=user,
        password=password,
        communicationTimeout=timeout_ms,
    )
    if encrypt:
        kwargs["encrypt"] = True
        kwargs["sslValidateCertificate"] = validate_cert
    conn = dbapi.connect(**kwargs)
    return HanaDB(conn, schema)


@contextmanager
def hana(*args, **kwargs) -> Iterator[HanaDB]:
    db = connect(*args, **kwargs)
    try:
        yield db
    finally:
        db.close()
