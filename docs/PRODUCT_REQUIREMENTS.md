# Stockroom product requirements

Stockroom supports one organization and warehouse managing dated inventory. It tracks physical and usable quantities by product and batch, suggests first-expiry-first-out picks, identifies replenishment needs, and records who changed stock and why.

## Inventory

Products have unique SKUs, optional barcodes, category, base unit, whole-unit or three-decimal quantity precision, expiry tracking, reorder thresholds, and archive status. Batches have product-specific unique lots, manufacture/expiry dates, supplier references, optional locations, and availability status.

Stock history is append-only. Movements include opening balance, receipt, issue, customer return, supplier return, write-off, adjustment, and guarded reversal. Exact quantities, transactional commands, retry safety, and concurrency protection prevent negative stock and partial postings.

Customer returns require an eligible issue and enter quarantine. Administrators review release, disposal, and corrections.

## Expiry and picking

The business timezone defaults to Europe/Istanbul. Batches expire after the end of the labelled expiry date. Usable stock excludes expired, quarantined, blocked, and archived inventory and applies minimum remaining shelf life.

FEFO uses earliest eligible expiry, deterministic ties, and receipt-order fallback for non-expiring stock. Posting revalidates availability. Expiry never deletes physical stock; disposal requires an explicit write-off.

## Workflows

- Responsive dashboard, product/batch details, stock movement forms, expiry filters, alerts, and audit log.
- Separate CSV/XLSX product and opening-stock imports with templates, column mapping, explicit date formats, preview, validation errors, and confirmed atomic commit.
- Filtered, formula-safe product, batch, and movement exports with stable identifiers and timezone metadata.
- Deduplicated low-stock and expiry alerts with acknowledgement, resolution, recurrence tracking, scheduled checks, and last-run status.
- Administrator, operator, and viewer roles enforced by the API, hashed passwords, and expiring sessions.

## Operation

React and TypeScript frontend, FastAPI backend, PostgreSQL persistence and migrations, Docker and local startup, fictional opt-in demo data, integration tests, and backup/restore guidance.

This version excludes accounting, manufacturing, marketplace synchronization, multiple organizations or warehouses, automated purchasing, complex unit conversions, and demand forecasting.

Detailed behavior is documented in DATA_MODEL.md, STOCK_RULES.md, IMPORT_EXPORT.md, and TEST_RESULTS.md.
