"""Output formatters: text table, JSON."""

import json
from datetime import date, datetime
from decimal import Decimal
from typing import List


def _coerce(val):
    """JSON-serializable coercion for HANA types (Decimal, date, datetime)."""
    if val is None:
        return None
    if isinstance(val, Decimal):
        # Decimals: keep precision via str (avoid float rounding).
        return str(val)
    if isinstance(val, (date, datetime)):
        return val.isoformat()
    if isinstance(val, (bytes, bytearray)):
        return val.hex()
    return val


def to_json(cols: List[str], rows: List[list], indent: int = 2) -> str:
    payload = [{c: _coerce(v) for c, v in zip(cols, row)} for row in rows]
    return json.dumps(payload, indent=indent)


def format_text_table(
    cols: List[str],
    rows: List[list],
    max_rows: int = 50,
    max_col_width: int = 40,
) -> str:
    """Pretty-print rows as an aligned text table."""
    if not cols:
        return "  (no results)"

    display_rows = rows[:max_rows]
    truncated = len(rows) > max_rows

    def fmt(val) -> str:
        if val is None:
            return "NULL"
        s = str(val)
        if len(s) > max_col_width:
            # Truncate to (max_col_width - 1) and append ellipsis,
            # so total width stays within max_col_width.
            return s[: max_col_width - 1] + "…"
        return s

    str_rows = [[fmt(c) for c in row] for row in display_rows]
    header = [fmt(c) for c in cols]

    widths = [len(h) for h in header]
    for row in str_rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))

    def row_str(cells):
        return "  " + " | ".join(c.ljust(w) for c, w in zip(cells, widths))

    lines = [row_str(header), "  " + "-+-".join("-" * w for w in widths)]
    for r in str_rows:
        lines.append(row_str(r))

    total = len(rows)
    if truncated:
        lines.append(f"\n  ... ({total} total rows, showing first {max_rows})")
    else:
        plural = "s" if total != 1 else ""
        lines.append(f"\n  ({total} row{plural})")

    return "\n".join(lines)
