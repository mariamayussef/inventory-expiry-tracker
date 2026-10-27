# Stock and expiry rules

## Exact quantities

API quantities are decimal strings (integers are also accepted). Binary float JSON quantities are rejected. Whole-unit products require integral quantities. Fractional products accept at most three decimal places, checked with Python Decimal before insertion into PostgreSQL `NUMERIC(18,3)`. Values must be finite, positive, and at most 999999999999999. Thresholds may be zero. No unit conversion is performed.

PostgreSQL documents NUMERIC as exact and notes that declared scales can round input; application validation therefore runs before storage: https://www.postgresql.org/docs/current/datatype-numeric.html.

## Posting and concurrency

Every stock command requires authentication, allowed role, reason, product, and `Idempotency-Key`. Fingerprints include the submitted command and actor identity. A successful retry returns the original response. Conflicting reuse returns HTTP 409. Failed commands roll back and can be corrected/retried. Product creation and import commit also support this contract. Use one key per intentional operation, retain it across network retries, and change it only after changing the intended input.

The product row is locked `FOR UPDATE` before computing ledger balances. PostgreSQL holds the lock until transaction end. Every deduction rechecks the balance while holding the lock; no physical balance can become negative through the API. Multi-batch issues post all lines or none. Imports lock products in a consistent order. Product-level serialization is intentionally conservative for a small warehouse.

Locking semantics and deadlock considerations: https://www.postgresql.org/docs/current/explicit-locking.html.

| Movement | Effect / permission |
| --- | --- |
| Receipt | Positive, administrator/operator, explicit lot and dates |
| Opening | Positive ledger entry, administrator; never overwrites balances |
| Issue | Negative FEFO lines, administrator/operator, confirmed preview required |
| Customer return | Positive into a newly generated quarantine lot, administrator/operator; must reference one eligible issue line |
| Supplier return | Negative physical stock from selected batch, administrator/operator |
| Write-off | Negative physical stock, administrator with reason, including expired/quarantined stock |
| Adjustment | Positive or negative, administrator; explicit add/remove, batch, reason; supports audited unlinked corrections |
| Reversal | Opposite effect of original, administrator; one reversal maximum, no reversal-of-reversal |

Returns cannot exceed issued quantity minus all already-linked returns. Issues with linked returns cannot be reversed. A reversed issue cannot receive a customer return. Customer-return movements cannot be reversed directly; review/write off the quarantine stock instead. All guards run while holding the product lock. Positive movements can be reversed only if enough physical stock remains. Partial return plus write-off is preserved as separate history.

Only administrators change batch availability, release quarantine, archive records, adjust stock, write off, or reverse. Availability changes are audited but do not move physical units. Operators receive/issue and perform linked customer/supplier returns; viewers are read-only. Backdating is disabled: timestamps always come from the database in UTC. Optional references do not set transaction time.

## Dates and FEFO

Business timezone defaults to Europe/Istanbul and is configurable. `business_today` is calculated on the server at request/check time. Expiry is stored as a date. **Expired means expiry_date < business_today**: the labelled expiry date remains eligible when minimum shelf life is zero. Expires-today has its own status. Minimum shelf life requires `expiry_date - business_today >= minimum_shelf_days`. Invalid dates and manufacture-after-expiry are rejected. Tracked products require expiry. Matching product/lot with conflicting dates returns a reviewable 409.

FEFO orders eligible stock by expiry date ascending, then batch creation time and UUID. Null expiry goes last with creation-order fallback. Barcode identifies only a product. Archived products, blocked/archived/quarantined batches, expired stock, and stock below minimum shelf life are excluded. Shortfalls are reported. The client confirms batch/quantity lines and the server recomputes them under lock. Changed suggestions return 409 and an updated suggestion; no partial issue is posted. Preview is not a reservation.

Physical includes every positive remaining unit regardless of status/expiry. Dashboard status precedence is batch availability (quarantine/blocked/archived), then expired, today, 1–7, 8–30, 31–60, 61–90, healthy, or non-expiring. Those quantity buckets do not overlap. Usable also excludes inactive products and minimum-life restrictions. Expiry never disposes of stock automatically. Low stock means usable <= threshold on active products.

## Alerts

Low stock condition is keyed by product; expiry condition by batch. Expiry includes physically present batches expiring in the configured window or already expired, including blocked/quarantined lots for disposal awareness. Scheduled and API checks use the same classification functions. Refreshing an unchanged condition preserves acknowledgement and occurrence count. A condition that disappears resolves; when it returns, the same alert reopens, clears acknowledgement, and increments occurrences. Acknowledgement does not change stock. Last-run timestamp updates only in a successful transaction. Startup reconciles; reading the alert center also reconciles. Correct dashboard expiry classification never depends on the worker.

`DEMO_TODAY` is an explicit demonstration/test override only. Never use it for operational stock.
