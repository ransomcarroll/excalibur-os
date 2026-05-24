# Tableau Details Purchase View With Items

**Type**: View
**Schema**: FTPROD2
**Role**: Canonical purchases fact view.

## Grain

One row per A/P document line.

## Use For

- Net purchases by vendor, manufacturer, item, product group, or procurement attribute.
- Purchase trend analysis paired with `Tableau Export View With Items`.
- Vendor/manufacturer spend analysis.

## Watch

- Includes A/P invoices and credit memos. Credit memos are signed negative.
- `DocType = 'I'` is item lines; `DocType = 'S'` is service lines.
- `CardCode` / `CardName` are the vendor paid.
- `Manufacturer` / `U_ManufAbbr` describe whose product was purchased.

## Key Columns

| Column | Meaning |
|---|---|
| `Type`, `DocType` | Document kind and item/service line type. |
| `DocDate`, `DocNum`, `DocEntry` | Purchase document date and identifiers. |
| `CardCode`, `CardName` | Vendor. |
| `ItemCode`, `Dscription` | SAP item and line description. |
| `Quantity`, `Price`, `Amount` | Signed purchase quantity, unit price, and line value. |
| `WhsCode` | Receiving warehouse on the line. |
| `ItmsGrpNam` | Product group; edgebanding filters usually use `LIKE '%Edgebanding%'`. |
| `Manufacturer`, `U_ManufAbbr` | Product manufacturer. |
| `U_Material`, `U_ColorSpeciesName`, `U_EbWidth`, `U_EbLfRoll` | Edgebanding item attributes from `OITM`. |
