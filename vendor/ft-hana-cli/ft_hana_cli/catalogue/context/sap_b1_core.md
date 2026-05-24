# SAP B1 Core Context

These are supporting tables, not catalogue entry points.

| Object | Role |
|---|---|
| `OITM` | Item master. Owns edgebanding UDFs. |
| `OITW` | Item stock by warehouse: `OnHand`, `OnOrder`, `IsCommited`, `AvgPrice` (canonical unit cost). |
| `OCRD` | Business partners: customers and vendors. |
| `ORDR` / `RDR1` | Sales order header / lines. |
| `OPOR` / `POR1` | Purchase order header / lines. |
| `ODLN` / `DLN1` | Delivery header / lines. |
| `OWOR` / `WOR1` | Production order header / components. Used for slitting and other production operations. |
| `OMRC` | Manufacturer master. Join from `OITM.FirmCode`. |
| `OITB` | Item groups. Edgebanding filters usually use `ItmsGrpNam LIKE '%Edgebanding%'`. |
| `ITM1` | Price lists. Standard price list is usually `PriceList = 1`. |
| `UFD1` | UDF valid values / descriptions. |
| `ProcurementCodes` | Procurement rollups by item. |
| `@MLMM` | Width reference table used for slitting. |
| `@SRCG` | Sourcing/manufacturer config. |

## Gotchas

- Quote identifiers: `FTPROD2."OITM"`.
- UDT names include `@`: `FTPROD2."@MLMM"`.
- Edgebanding sub items usually live in `OITM` with `ItmsGrpCod = 112`.
- Open sales orders use `ORDR` + `RDR1`; open purchase orders use `OPOR` + `POR1`.
- Common open-line filter: line `OpenQty > 0`; header cancel logic varies by document type.
- **Inventory cost = `OITW."AvgPrice"`**. Never `OITM."LastPurPrc"` (often null/stale). See the `costing` context.
- **EdgeCo acquisition (2026-01-01).** FT sales views (`Tableau Export View With Items`, `OINV`/`INV1`, etc.) include EdgeCo only from 2026 onward — pre-2026 EdgeCo activity is **not** in the FT books. Any YoY / trend that crosses 2026-01-01 will overstate FT growth. For company-level trend across the boundary, use `Frama_EdgeCo_combined_sales`.
- Do not treat this file as an allowlist. HANA grants are the security boundary.
