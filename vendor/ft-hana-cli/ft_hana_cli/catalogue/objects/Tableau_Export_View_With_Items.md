# Tableau Export View With Items

**Type**: View
**Schema**: FTPROD2
**Role**: Canonical sales fact view.

## Grain

One row per sales document line.

## Use For

- Sales history by customer, item, salesperson, product group, or procurement code.
- Trailing-window demand: T3Mo / T6Mo / T12Mo quantity, frequency, dispersion.
- Reorder, commission, KAM, and sales analytics inputs.

## Watch

- `ItemCode = 'SHIPPING'` is a freight pseudo-line; exclude it from item demand.
- Credit memos are signed negative. `SUM("Amount")` returns net sales.
- `OnHand`, `OnOrder`, `IsCommited` are current inventory snapshots, not historical state.
- `ProcurementCodeLf`, `ProcurementCodeLfMM`, and `ProcurementCodeSqm` are already denormalized.
- `SalesCost` is unit cost. Use `SUM("Quantity" * "SalesCost")` for COGS.
- **FT-only.** Frama-Tech acquired EdgeCo on 2026-01-01, so 2026+ includes
  the EdgeCo book but 2024-2025 do not. YoY / growth comparisons that cross
  2026-01-01 will overstate growth. For company-level trend across the
  acquisition boundary, use `Frama_EdgeCo_combined_sales`.

## Key Columns

| Column | Meaning |
|---|---|
| `DocDate`, `ShipDate` | Document date and planned ship date. |
| `CardCode`, `CardName`, `CardType` | Customer identity. |
| `ItemCode`, `Dscription` | SAP item and line description. |
| `Quantity`, `Amount`, `OpenQty` | Line quantities and value. |
| `ItmsGrpNam`, `GroupCode` | Product group; edgebanding filters usually use `LIKE '%Edgebanding%'`. |
| `ProcurementCodeLf`, `ProcurementCodeLfMM`, `ProcurementCodeSqm` | Procurement rollups. |
| `U_DefaultWarehouse` | Frama item/customer assignment context; not necessarily the warehouse used on a document line. |
| `SlpCode`, `SlpName` | Salesperson. |

## Subs

Match-substitution lines: a physical item shipped in lieu of the decor the
customer ordered. ~10% of lines are subs. Get this wrong and you double-count
demand or attribute sales to the wrong color. See `edgebanding` context for the
underlying mechanics; this section is about column behavior on this view.

**Discriminator**: `U_SubbedFor IS NOT NULL AND U_SubbedFor <> ''`. Both NULL
and empty-string non-subs exist — check both.

**Column duality on a sub line**:

| Identity | Physical (what shipped) | Sold-as (what customer ordered) |
|---|---|---|
| ItemCode | `ItemCode` | `U_SubbedFor` |
| Description | `Dscription` | `U_SubDescription` |
| Color/species | `U_ColorSpeciesName` | `U_SubColorSpeciesName` |
| Finish abbr | `U_EbFinishAbbr` | `U_SubEbFinishAbbr` |
| Full finish | `U_EbFinish` | `U_SubEbFinish` |
| Long CSN | `U_LongCSN` | `U_SubLongCSN` |
| CSN desc | `U_CSNDesc` | `U_SubCSNDesc` |
| Brand | `U_LaminateBrand` | `SubLaminateBrand` |

On non-sub lines all `U_Sub*` / `Sub*` columns are NULL.

**Grouping rules**:

- Customer-facing demand (what colors are selling): group by
  `COALESCE(NULLIF(U_SubColorSpeciesName,''), U_ColorSpeciesName)` — counts
  W7937 sold as Tafisa 592 toward Tafisa 592 demand, not W7937.
- Physical movement / sourcing / inventory consumption: group by `ItemCode` or
  `U_ColorSpeciesName` straight — counts the same line toward W7937.
- Flywheel coverage: split self vs sub revenue by
  `CASE WHEN U_SubbedFor IS NULL OR U_SubbedFor = '' THEN 'self' ELSE 'sub' END`.

**Watch**:

- `U_SubSurcharge` is a price multiplier (e.g. `1.22` = +122%), already applied
  to `Price` and therefore to `Amount`. Don't add it again.
- `SubFoundProactively` ('Y'/'N') flags whether the sub was suggested
  proactively vs reactively at order entry. Useful for measuring proactive-sub
  program lift; not needed for demand math.
- A "What did we sell of color X?" query that filters only on
  `U_ColorSpeciesName = 'X'` will miss X sold as a sub of something else, and
  will count X-sold-as-Y toward X. Decide which side you want before writing
  the filter.
