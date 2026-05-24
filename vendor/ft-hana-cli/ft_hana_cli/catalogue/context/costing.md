# Costing Context

## Inventory cost — canonical source

Always use `OITW."AvgPrice"` as the unit cost for inventory valuation,
COGS approximations, and any cost-weighted on-hand math.

`OITW` is item-by-warehouse, so the cost is warehouse-specific and reflects
the moving average maintained by SAP B1.

```sql
SELECT
  w."ItemCode",
  w."WhsCode",
  w."OnHand",
  w."AvgPrice"                              AS unit_cost,
  w."OnHand" * w."AvgPrice"                 AS inventory_value
FROM FTPROD2."OITW" w
WHERE w."OnHand" > 0
```

## Do not use

- `OITM."LastPurPrc"` — last purchase price. Frequently null or stale.
  Not a valuation field. Using it silently understates or zeroes out cost.
- `OITM."AvgPrice"` — item-level average across warehouses. Use only when
  you explicitly want a company-wide average and have no warehouse context.
  Default to `OITW."AvgPrice"`.
- Document-line prices (`POR1.Price`, `RDR1.Price`, etc.) — these are
  transaction prices, not inventory cost.

## Why this matters

A prior analysis used `LastPurPrc` and produced wrong cost figures because
the column is empty for many items. `OITW.AvgPrice` is the only field SAP
maintains as the running cost. Treat it as the single source of truth for
"what is this inventory worth" questions.
