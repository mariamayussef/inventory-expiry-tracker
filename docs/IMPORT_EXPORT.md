# Imports and exports

## Supported imports

Two intentionally separate kinds:

- `products`: new master records. Columns: sku, name, category, barcode, unit, whole_units, expiry_tracked, threshold. Existing SKU/barcode is a conflict, not an implicit update.
- `opening`: positive opening movements against known SKUs. Columns: sku, lot, expiry_date, manufacture_date, quantity, supplier, location, reference, reason. No unknown products are created. Opening quantity is additive, never a balance replacement.

Download CSV or XLSX templates in the UI or `/api/templates/products?format=xlsx`. Example CSV files are in `templates/`. Use the product import first for unknown SKUs, then a separate opening import.

1. Administrator chooses a CSV/XLSX file, import kind, explicit date interpretation, and optional mapping from target field to exact source header (e.g. `{"sku":"Item Code"}`).
2. UTF-8 CSV or the first worksheet of XLSX is read. Limit 2 MB compressed, 12 MB expanded workbook content, 500 data rows. Formula text is treated as data and never evaluated.
3. ISO `YYYY-MM-DD` is default. `DD/MM/YYYY` or `MM/DD/YYYY` must be selected explicitly. Native XLSX date cells are normalized to ISO. No string date guessing. Decimal values use a dot and no thousands separators. For exact fractional amounts, format XLSX quantity cells as text; Python converts native numeric cells to decimal strings for the same scale validation, but cannot recover precision Excel has already lost.
4. Full-batch preview validates rows using the same stock rules in rolled-back savepoints; preview never posts stock. Duplicate SKU (master) or SKU/lot (opening) within the file is an error. Existing lot-date conflicts and existing master SKUs are errors. The response includes stable import ID, normalized rows and row-numbered errors.
5. Confirm explicitly with `{"confirm":true}` and an idempotency key. The server locks the stage, revalidates current records, and commits every row in one transaction. Any failure rolls back all rows. Correct the file and stage again after errors.
6. Retry the same staged import safely. Committed import IDs cannot post twice, even with a new key. Staging the same file as an entirely new import is a new intentional import, so review it before confirming.

Preview UI shows the first 25 normalized rows and all validation errors; all staged rows are validated and committed. This version has no automatic chunking, arbitrary historical movement import, or product upsert.

## Exports

CSV/XLSX exports cover product stock, batch expiry and movement history. Use list Export for the active search/status filters. Dedicated unfiltered downloads also exist on Imports & exports. Endpoints support product_id, batch_id and movement type filters where relevant. Exported records include stable IDs, unambiguous ISO dates, UTC movement timestamps, business timezone/date, shelf-life setting and expiry policy. Movement exports are capped at the newest 5,000 matching rows, matching the API list cap. Empty exports have a no_results header.

Text beginning with `=`, `+`, `-`, `@`, tab or carriage return (including after whitespace) is prefixed with an apostrophe in CSV/XLSX. This includes negative ledger effects: spreadsheet cells are deliberately text for formula safety and exactness. Import/export never executes spreadsheet formulas. Do not remove escaping on untrusted text.

## HTTP contract examples

```
POST /api/imports/preview (multipart: file, kind, mapping, date_format)
POST /api/imports/{id}/commit
Idempotency-Key: import-{id}
Content-Type: application/json
{"confirm":true}

GET /api/export/batches?status=expired&q=milk&format=xlsx
GET /api/export/movements?product_id={uuid}&type=issue&format=csv
```
