"""ft-hana-cli — read-only SAP HANA query CLI for Frama-Tech FTPROD2."""

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

from ft_hana_cli import __version__
from ft_hana_cli.db import hana
from ft_hana_cli.catalogue import (
    get_context,
    get_profile,
    has_profile,
    list_contexts,
    list_profiles,
)
from ft_hana_cli.output import format_text_table, to_json


# ---------------------------------------------------------------------------
# Env loading: --env-file > $FT_HANA_ENV_FILE > ~/.ft-hana/hana.env > ./.env
# ---------------------------------------------------------------------------
def _load_env(explicit_path: Optional[str]) -> Optional[Path]:
    candidates = []
    if explicit_path:
        candidates.append(Path(explicit_path).expanduser())
    elif os.environ.get("FT_HANA_ENV_FILE"):
        candidates.append(Path(os.environ["FT_HANA_ENV_FILE"]).expanduser())
    else:
        candidates.append(Path.home() / ".ft-hana" / "hana.env")
        candidates.append(Path.cwd() / ".env")

    for path in candidates:
        if path.is_file():
            load_dotenv(path, override=False)
            return path
    return None


def _require_env() -> dict:
    missing = [
        v for v in ("HANA_HOST", "HANA_USER", "HANA_PASSWORD") if not os.environ.get(v)
    ]
    if missing:
        sys.stderr.write(
            "Error: missing HANA credentials in env: " + ", ".join(missing) + "\n"
            "Set them in ~/.ft-hana/hana.env or pass --env-file <path>.\n"
            "Required: HANA_HOST, HANA_USER, HANA_PASSWORD\n"
            "Optional: HANA_PORT (default 30015), HANA_SCHEMA (default FTPROD2),\n"
            "          HANA_ENCRYPT (default false)\n"
        )
        sys.exit(2)

    encrypt_raw = os.environ.get("HANA_ENCRYPT", "false").strip().lower()
    return dict(
        host=os.environ["HANA_HOST"],
        port=int(os.environ.get("HANA_PORT", "30015")),
        user=os.environ["HANA_USER"],
        password=os.environ["HANA_PASSWORD"],
        schema=os.environ.get("HANA_SCHEMA", "FTPROD2"),
        encrypt=encrypt_raw in ("1", "true", "yes", "on"),
    )


def _env_show_all() -> bool:
    return os.environ.get("FT_HANA_SHOW_ALL", "").strip().lower() in ("1", "true", "yes", "on")


def _emit(cols, rows, fmt: str, max_rows: int = 50, max_col_width: int = 40) -> None:
    if fmt == "json":
        print(to_json(cols, rows))
    else:
        print(format_text_table(cols, rows, max_rows=max_rows, max_col_width=max_col_width))


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------
def cmd_query(args, conn_kwargs):
    if args.file:
        sql_text = Path(args.file).read_text(encoding="utf-8")
    elif args.sql:
        sql_text = args.sql
    else:
        sys.stderr.write("Error: provide SQL inline or with --file\n")
        sys.exit(2)

    if args.schema:
        conn_kwargs["schema"] = args.schema

    with hana(**conn_kwargs) as db:
        cols, rows = db.query(sql_text)
    _emit(cols, rows, args.format, max_rows=args.max_rows, max_col_width=args.max_col_width)


def cmd_tables(args, conn_kwargs):
    if args.schema:
        conn_kwargs["schema"] = args.schema
    with hana(**conn_kwargs) as db:
        cols, rows = db.list_tables(args.pattern)

    show_all = args.all or _env_show_all()
    if not show_all:
        rows = [r for r in rows if has_profile(r[1])]

    if args.format == "text":
        if show_all:
            annotated_cols = cols + ["Catalogue?"]
            annotated_rows = [r + [("yes" if has_profile(r[1]) else "")] for r in rows]
            print(format_text_table(annotated_cols, annotated_rows, max_rows=args.max_rows))
        else:
            print(format_text_table(cols, rows, max_rows=args.max_rows))
            if not rows:
                print("\n  (no catalogue objects match this pattern. Use --all to see everything.)")
    else:
        out = []
        for r in rows:
            d = {c: v for c, v in zip(cols, r)}
            d["has_catalogue_profile"] = has_profile(r[1])
            out.append(d)
        import json
        print(json.dumps(out, indent=2, default=str))


def cmd_describe(args, conn_kwargs):
    if args.schema:
        conn_kwargs["schema"] = args.schema

    show_all = args.all or _env_show_all()
    if not has_profile(args.table) and not show_all:
        sys.stderr.write(
            f"Error: {args.table!r} is not in the catalogue.\n"
            f"Use --all to describe non-catalogue objects, or run "
            f"`ft-hana-cli catalogue --list`.\n"
        )
        sys.exit(1)

    with hana(**conn_kwargs) as db:
        col_cols, col_rows = db.columns_of(args.table)
        if not col_rows:
            sys.stderr.write(f"Error: table or view not found: {args.table}\n")
            sys.exit(1)
        sample_cols, sample_rows = db.sample_rows(args.table, args.samples)

    profile = get_profile(args.table)

    if args.format == "json":
        import json
        payload = {
            "table": args.table,
            "schema": conn_kwargs["schema"],
            "columns": [
                {c: v for c, v in zip(col_cols, row)} for row in col_rows
            ],
            "sample": [
                {c: v for c, v in zip(sample_cols, row)} for row in sample_rows
            ],
            "catalogue_profile": profile,
        }
        print(json.dumps(payload, indent=2, default=str))
        return

    print(f"\n{'=' * 70}")
    print(f"  {conn_kwargs['schema']}.\"{args.table}\"")
    print(f"{'=' * 70}\n")

    print("COLUMNS")
    print(format_text_table(col_cols, col_rows, max_rows=500))
    print()

    print(f"SAMPLE ({args.samples} rows)")
    print(format_text_table(sample_cols, sample_rows, max_rows=args.samples,
                            max_col_width=args.max_col_width))
    print()

    if profile:
        print("CATALOGUE")
        print("-" * 70)
        print(profile.rstrip())
        print()
    elif not args.no_catalogue_hint:
        print("CATALOGUE")
        print("-" * 70)
        print(f"  (no catalogue profile for {args.table!r})")
        print()


def cmd_columns(args, conn_kwargs):
    if args.schema:
        conn_kwargs["schema"] = args.schema
    with hana(**conn_kwargs) as db:
        cols, rows = db.search_columns(args.pattern)

    show_all = args.all or _env_show_all()
    if not show_all:
        catalogue = set(list_profiles())
        rows = [r for r in rows if r[0] in catalogue]

    _emit(cols, rows, args.format, max_rows=args.max_rows)
    if args.format == "text" and not show_all and not rows:
        print("\n  (no matches in catalogue objects. Use --all to search everything.)")


def cmd_catalogue(args, conn_kwargs):
    target = args.target or []
    if target and target[0] == "context":
        if args.list:
            names = list_contexts()
            if args.format == "json":
                import json
                print(json.dumps(names, indent=2))
            else:
                if not names:
                    print("  (no catalogue context)")
                    return
                print("Catalogue context:")
                for name in names:
                    print(f"  - {name}")
            return

        name = target[1] if len(target) > 1 else "edgebanding"
        context = get_context(name)
        if context is None:
            sys.stderr.write(f"Error: no catalogue context for {name!r}.\n")
            sys.exit(1)

        if args.format == "json":
            import json
            print(json.dumps({"name": name, "catalogue_context": context}, indent=2))
        else:
            print(context.rstrip())
        return

    if args.list:
        names = list_profiles()
        if args.format == "json":
            import json
            print(json.dumps(names, indent=2))
        else:
            if not names:
                print("  (catalogue is empty)")
                return
            print("Catalogue objects:")
            for name in names:
                print(f"  - {name}")
        return

    if not target:
        sys.stderr.write("Error: provide an object name, run `catalogue --list`, or run `catalogue context --list`\n")
        sys.exit(2)

    table = " ".join(target)
    profile = get_profile(table)
    if profile is None:
        sys.stderr.write(f"Error: no catalogue profile for {table!r}.\n")
        sys.exit(1)

    if args.format == "json":
        import json
        print(json.dumps({"table": table, "catalogue_profile": profile}, indent=2))
    else:
        print(profile.rstrip())


# ---------------------------------------------------------------------------
# Argparse setup
# ---------------------------------------------------------------------------
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="ft-hana-cli",
        description="Read-only SAP HANA query CLI for Frama-Tech (FTPROD2).",
    )
    p.add_argument("--version", action="version", version=f"ft-hana-cli {__version__}")
    p.add_argument("--env-file", help="Path to .env file with HANA_* vars")
    p.add_argument("--schema", help="Override HANA_SCHEMA (default FTPROD2)")
    p.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )

    sub = p.add_subparsers(dest="command", required=True, metavar="{query,tables,describe,columns,catalogue}")

    # query
    q = sub.add_parser("query", help="Run a SQL query")
    q.add_argument("sql", nargs="?", help="Inline SQL string")
    q.add_argument("--file", help="Read SQL from file")
    q.add_argument("--max-rows", type=int, default=50, help="Max rows to display (default 50)")
    q.add_argument("--max-col-width", type=int, default=40, help="Max column width in text output (default 40)")
    q.set_defaults(func=cmd_query)

    # tables
    t = sub.add_parser("tables", help="List tables and views in the schema")
    t.add_argument("pattern", nargs="?", default="%", help="LIKE pattern (default %%)")
    t.add_argument("--max-rows", type=int, default=500)
    t.add_argument("--all", action="store_true",
                   help="Include objects outside the catalogue")
    t.set_defaults(func=cmd_tables)

    # describe
    d = sub.add_parser("describe", help="Show columns, sample rows, and catalogue profile")
    d.add_argument("table", help="Table or view name (case-sensitive)")
    d.add_argument("--samples", type=int, default=3, help="Sample rows to fetch (default 3)")
    d.add_argument("--max-col-width", type=int, default=30)
    d.add_argument("--no-catalogue-hint", action="store_true",
                   help="Suppress the missing-catalogue message")
    d.add_argument("--all", action="store_true",
                   help="Allow describing objects outside the catalogue")
    d.set_defaults(func=cmd_describe)

    # columns
    c = sub.add_parser("columns", help="Find tables/views containing columns matching a name")
    c.add_argument("pattern", help="LIKE pattern, e.g. 'U_Eb%%' or 'CardCode'")
    c.add_argument("--max-rows", type=int, default=200)
    c.add_argument("--all", action="store_true",
                   help="Search objects outside the catalogue too")
    c.set_defaults(func=cmd_columns)

    # catalogue
    n = sub.add_parser("catalogue", help="Read the semantic catalogue")
    n.add_argument("target", nargs="*", help="Object name, or `context [name]`")
    n.add_argument("--list", action="store_true", help="List catalogue objects or contexts")
    n.set_defaults(func=cmd_catalogue)

    return p


def main(argv=None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    _load_env(args.env_file)

    # `catalogue` is the only subcommand that doesn't need DB credentials.
    if args.command == "catalogue":
        args.func(args, conn_kwargs={})
        return

    conn_kwargs = _require_env()
    args.func(args, conn_kwargs)


if __name__ == "__main__":
    main()
