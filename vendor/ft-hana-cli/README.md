# ft-hana-cli

Read-only SAP HANA CLI for Frama-Tech agents and analysts.

The CLI exposes a small, stable surface over `FTPROD2`: raw read queries,
schema inspection, column search, and a semantic catalogue for the two
canonical analytics views.

## Install

```bash
cd ft-hana-cli
pip install -e .
```

This registers `ft-hana-cli`.

## Configure

Credential lookup order:

1. `--env-file <path>`
2. `$FT_HANA_ENV_FILE`
3. `~/.ft-hana/hana.env`
4. `./.env`

Required:

```bash
HANA_HOST=...
HANA_USER=...
HANA_PASSWORD=...
```

Optional:

```bash
HANA_PORT=30015
HANA_SCHEMA=FTPROD2
HANA_ENCRYPT=false
```

Use a HANA user with `SELECT` only.

## Commands

```bash
ft-hana-cli query "SELECT TOP 5 * FROM FTPROD2.\"OITM\""
ft-hana-cli query --file query.sql --max-rows 100

ft-hana-cli tables
ft-hana-cli tables --all

ft-hana-cli describe "Tableau Export View With Items"
ft-hana-cli describe OITM --all

ft-hana-cli columns "U_Eb%"
ft-hana-cli columns CardCode --all

ft-hana-cli catalogue --list
ft-hana-cli catalogue "Tableau Details Purchase View With Items"
ft-hana-cli catalogue context --list
ft-hana-cli catalogue context edgebanding
```

Use `--format json` for agent/tooling output.

## Catalogue

The catalogue is the semantic layer: compact business profiles for canonical
HANA objects. It is intentionally small.

Current catalogue objects:

- `Tableau Export View With Items` - canonical sales fact view.
- `Tableau Details Purchase View With Items` - canonical purchases fact view.

By default, `tables`, `describe`, and `columns` operate on catalogue objects.
Use `--all` when exploring the wider schema.

Profiles live in:

```text
ft_hana_cli/catalogue/objects/
```

Compact domain context lives in:

```text
ft_hana_cli/catalogue/context/
```

## Security

The database role is the security boundary. The CLI is an ergonomic layer.

- Use a dedicated read-only HANA user.
- Grant only approved tables/views.
- Treat `--all` as exploration, not access control.
- Do not distribute write-capable credentials.

## Layout

```text
ft-hana-cli/
├── README.md
├── pyproject.toml
└── ft_hana_cli/
    ├── cli.py
    ├── db.py
    ├── output.py
    ├── catalogue.py
    └── catalogue/
        └── objects/
            ├── Tableau_Export_View_With_Items.md
            └── Tableau_Details_Purchase_View_With_Items.md
```
