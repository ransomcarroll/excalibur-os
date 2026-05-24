# Production Slitting Context

Frama-Tech uses SAP B1 production orders to represent edgebanding operations
that are often disassembly, not assembly.

Traditional ERP production: multiple components become one finished item.

Slitting: one wider roll becomes one or more narrower output items. The web
app orchestrator creates and closes multiple normal SAP production orders in
sync to model that physical reality.

## Core Tables

| Object | Role |
|---|---|
| `OWOR` | Production order header. One output item per row. |
| `WOR1` | Production order components. For slitting, usually the source roll. |

## OWOR UDFs

| Field | Meaning |
|---|---|
| `U_MasterWorkOrder` | Orchestrator key tying related SAP production orders together. Do not treat as a reliable FK to `OWOR.DocEntry`. |
| `U_Method` | Operation type. Values include `Master_Roll`, `Trimming`, `Preglue`, `Embossing`, `Digital`, `PSA`. |
| `U_Rolls` | Output roll count. |
| `U_FeetPerRoll` | Output feet per roll. |

## WOR1 UDFs

| Field | Meaning |
|---|---|
| `U_NominalQty` | Nominal component quantity. |
| `U_BOMRolls` | Source roll count represented in the BOM line. |
| `U_BOMFeetPerRoll` | Source feet per roll represented in the BOM line. |

## Slitting Shape

For each child `OWOR` row:

- `OWOR.ItemCode` = output item produced.
- `OWOR.PlannedQty` / `CmpltQty` = output LF.
- `WOR1.ItemCode` = source/master item consumed.
- `WOR1.PlannedQty` / `IssuedQty` = source LF consumed.
- `WOR1.BaseQty` approximates output width / source width.

One `U_MasterWorkOrder` may have multiple `OWOR` children, each producing a
different output width from the same source roll. Summing child output LF can
exceed source LF because narrower widths multiply usable lineal feet.

## Analysis Grain

Use `U_MasterWorkOrder` for job-level analysis.

Use `OWOR.DocEntry` / `DocNum` for SAP production-order-level analysis.

Use `WOR1` joined to `OITM` when you need source width, material, color,
finish, thickness, or source square meters.

For warehouse trend analysis, group by:

- `OWOR.PostDate`
- `OWOR.Warehouse`
- `OWOR.U_Method`
- `COUNT(DISTINCT OWOR.U_MasterWorkOrder)`
- output LF / SQM from `OWOR`
- source LF / SQM from `WOR1`

For slitting specifically, start with `U_Method IN ('Master_Roll','Trimming')`
and verify edge cases before excluding the other methods.
