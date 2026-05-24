# Edgebanding Context

## Strategy Lens

Frama-Tech is edgebanding-only. Most analysis should support speed,
availability, and service.

The PVC flywheel has four primitives:

1. Stock canonical colors in all sizes.
2. Sell canonical colors as subs for other colors.
3. Slit wider rolls into narrower widths.
4. Make to order only after stock, sub, and slit are exhausted.

Useful slices usually answer one of these questions:

- What do we sell by decor/color, finish, thickness bucket, width, brand, or customer?
- What do we have available by thickness bucket and square meters?
- Which demand is covered by self stock, subs, slit, or MTO?
- Which non-canon / limbo colors have enough volume, dispersion, or SQM to consider for canon?

## Item Identity

Edgebanding SKUs are mostly defined by `OITM` UDFs:

| Field | Meaning |
|---|---|
| `U_ColorSpeciesName` | Color/species identity. |
| `U_EbFinishAbbr` | Finish code; default nulls to `Stnd`. |
| `U_EbWidth` | Display width. |
| `U_EbWidthMMAprox` | Width bucket used for slitting. |
| `U_EbWidthMMExact` | Exact width used for square-meter math. |
| `U_EbThickness` | Thickness code. |
| `U_EbThicknessMM` | Numeric thickness. |
| `U_Material` | PVC, ABS, Veneer, Melamine, etc. |
| `U_BackerAdhesion` | Auto, Preglued, PSA. |
| `U_EbLfRoll` | Roll length in lineal feet. |
| `U_PeelCoat` | Peel coat flag. |
| `U_VeCut`, `U_VeFaceAttributes`, `U_GrainDirection` | Veneer attributes. |
| `U_ManufAbbr`, `FirmCode` | Manufacturer identity. |

### Item Description Format

`Dscription` / `ItemName` is deterministically assembled from item UDFs. Parse
back to fields rather than guessing.

Plastic edgebanding template:

```
{U_LongCSN}:{U_EbWidth}-{U_EbThickness}-{U_EbLfRoll}-{U_BackerAdhesion}-{U_EbFinishAbbr}-{U_ManufAbbr}-{U_Material}[-{U_PeelCoat}] {U_CSNDesc} **{U_EbFinish}**
```

Example: `Egger H3710:15/16-1mm-300-Auto-St12-Er-PVC Natural Carini Walnut **St12 Omnipore Matt Finish**`
→ `U_EbFinishAbbr='St12'`, `U_ManufAbbr='Er'` (Egger Roma).

Veneer template differs — uses `U_VeCut`, `U_VeFaceAttributes`, and
`U_GrainDirection` in place of `U_ManufAbbr` and adds a `Cut` suffix.

When in doubt about a token, query the UDFs by `ItemCode` instead of parsing
the description string.

## Manufacturer vs Decor

The same customer-facing color / finish / size may exist from multiple
manufacturers. Manufacturer identity lives through `OITM.FirmCode` joined to
`OMRC`.

When the question is product-market demand, aggregate across manufacturers:

- "How much F949 Matte Thin do we sell?"
- "How much white matte thin inventory exists?"
- "Which decors have enough demand to join the canon?"

When the question is sourcing, quality, margin, or vendor concentration, keep
manufacturer separate.

## Thickness

For edgebanding analytics, thin gauges roll up together:

```sql
CASE
  WHEN "U_EbThickness" IN ('018','020','021','022','024','028','030') THEN 'Thin'
  WHEN "U_EbThicknessMM" >= 1 AND "U_EbThicknessMM" < 1.5 THEN '1mm'
  WHEN "U_EbThicknessMM" >= 1.5 AND "U_EbThicknessMM" < 3 THEN '2mm'
  WHEN "U_EbThicknessMM" >= 3 THEN '3mm'
END
```

## Square Meters

Purchasing often works at square-meter level because inventory is semi-fungible
inside a thickness bucket. Use exact width for conversion:

```sql
("U_EbWidthMMExact" / 1000.0) * "Quantity" * 0.3048
```

Use the same expression for sold, purchased, on-hand, on-order, and committed
quantities. Group by material, manufacturer, color/species, finish, and
thickness bucket depending on the question.

For purchasing and inventory planning, square meters by thickness bucket are
often more coherent than lineal feet by SKU. Slitting makes widths
semi-fungible inside a compatible color / finish / material / manufacturer
group, so width-specific SKU counts can understate true coverage.

## Slitting

Slitting means a wider roll can fulfill demand for a narrower width.

Core rule:

```sql
FLOOR(SourceWidthMM / TargetWidthMM) * SourceQty
```

Use `U_EbWidthMMAprox` for source/target width comparison. Use `FLOOR` or
HANA `ROUND(value, 0, ROUND_DOWN)`. Never round up.

Same-width stock is pick quantity. Strictly wider stock is slit quantity.

Slitting match keys:

- `U_ColorSpeciesName`
- `U_EbFinishAbbr` with null treated as `Stnd`
- thickness bucket
- manufacturer / `FirmCode`
- `U_BackerAdhesion`
- warehouse, when calculating warehouse-specific availability
- veneer cut for veneer items

Veneer nuance: thin, 1mm, and 1.5mm veneer can be slit. 3mm veneer should not
be treated as slittable.

## Subs

Subs are match-substitution items. A physical item is sold as another
customer-facing color/decor when the match is close enough.

Example: physical `F949 Matte` inventory can be sold as `Tafisa 100` if the
visual match is approved. The customer-facing item, invoice description, and
front-end data are masked as the subbed-for decor; the warehouse fulfills with
the physical item.

Subs are widespread and strategic. They let Frama-Tech serve thousands of
colors while stocking hundreds.

SAP patterns:

- Match-sub items are `OITM.ItmsGrpCod = 112`.
- `SWW` points to the real item's `U_ColorSpeciesName`.
- `U_SWWFinish` points to the real item's `U_EbFinish`.
- `U_MatchSubSurcharge` stores the price premium.
- Sales/order lines may expose `U_SubbedFor` and `U_SubDescription`.

Analysis rule:

- For customer-facing demand, group by the sold-as / subbed-for decor when
  available.
- For physical inventory, procurement, warehouse work, and sourcing, group by
  the real physical item.
- When measuring flywheel coverage, separate self revenue from sub revenue.

## Warehouses

`WhsCode` is the actual warehouse on stock or a document line.

`U_DefaultWarehouse` is the demand/default assignment used for planning; it is
not necessarily where the line actually shipped from. In demand planning,
`U_DefaultWarehouse` represents the optimal/default warehouse for the customer
or item context.

US warehouse families:

| Physical | Transit |
|---|---|
| `DFW-02` | `TRAN-DFW` |
| `LAX-02` | `TRAN-LAX` |
| `ORD-02` | `TRAN-ORD` |
| `LGA-02` | `TRAN-LGA` |

Transit warehouses usually collapse into the destination warehouse for stock
position.
