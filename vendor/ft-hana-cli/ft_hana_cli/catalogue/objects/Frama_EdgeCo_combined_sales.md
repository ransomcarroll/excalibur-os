# Frama_EdgeCo_combined_sales

**Type**: View
**Schema**: FTPROD2
**Role**: Acquisition-normalized company sales fact for YoY across the EdgeCo boundary.

## Why this view exists

Frama-Tech acquired EdgeCo effective 2026-01-01. Post-acquisition the EdgeCo
book flows through FT and is present in the canonical sales view
(`Tableau Export View With Items`). Pre-acquisition (2024, 2025), EdgeCo sold
under its own entity and is **not** present in the FT books.

Any growth / YoY trend pulled from the FT-only sales view that crosses
2026-01-01 will overstate growth because the 2025 baseline is missing the
EdgeCo book. This view stitches FT history together with an estimate of
EdgeCo's 2024–2025 sales so company-level trend has an apples-to-apples
baseline.

## Grain

Mixed by `Source`:

- `Source = 'FT'` — one row per sales document line. Invoices and Credit
  Memos. 2021-08-28 → present. `DocNum` populated.
- `Source = 'EdgeCo'` — one row per **daily per-customer estimate**. Invoices
  only. 2024-01-01 → 2025-12-31. `DocNum` is NULL.

Treat the EdgeCo side as a customer/day-level estimate, not transactional
truth.

## Use For

- Company-level sales trend, growth %, YoY across 2026-01-01.
- Customer activity that must include pre-acquisition EdgeCo behavior.
- Salesperson / segment rollups on the FT side.

## Do not use for

- Item, decor, thickness, width, or SKU-level analysis — no item info on
  either side, and no item info on the EdgeCo side period. Use
  `Tableau Export View With Items` for item-grain questions and accept that
  it omits EdgeCo's pre-2026 book.

## Watch

- `Source IN ('FT','EdgeCo')` is the discriminator. Always filter or pivot
  on it when the answer depends on attribution.
- EdgeCo rows: `DocNum` NULL, `SlpName` is mostly `'-No Sales Employee-'`,
  `Type` is always `'Invoice'`, `GroupName` is the customer's FT-side group.
- EdgeCo has no Credit Memos. FT side does, and credit-memo `Amount` is
  signed negative — `SUM("Amount")` returns net.
- 2026 has zero `Source = 'EdgeCo'` rows by design; post-acquisition
  activity is already inside FT.
- `Year` and `Month` are denormalized off `DocDate`.

## Key Columns

| Column | Meaning |
|---|---|
| `Source` | `'FT'` or `'EdgeCo'`. Acquisition-aware discriminator. |
| `Type` | `'Invoice'` or `'Credit Memo'`. EdgeCo is always `'Invoice'`. |
| `DocDate` | Document date (FT) or day of estimate (EdgeCo). |
| `DocNum` | FT document number. NULL for EdgeCo. |
| `CardCode`, `CardName` | Customer identity. |
| `SlpName` | Salesperson (FT). EdgeCo is mostly `'-No Sales Employee-'`. |
| `GroupName` | Customer group / segment. |
| `Amount` | Line / daily-estimate amount. Credit memos are signed negative. |
| `Year`, `Month` | Denormalized from `DocDate`. |
