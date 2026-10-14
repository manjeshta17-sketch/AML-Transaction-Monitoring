# Phase 5.2A — Production Multi-File Hardening Report

## 1. Problem identified in Phase 5.2

Phase 5.2 verified that the application is a persistent transaction
population. Different uploads are appended and monitoring reevaluates all
persisted transactions. Non-null `Ext Txn Id` values are skipped when already
present, but blank/null external IDs can be imported repeatedly.

The prior implementation also had no persistent upload, file, or batch
identity. As a result, an analyst could not distinguish the originating file
for a transaction, alert, or enrichment through stored metadata.

## 2. Current behavior before hardening

Before this phase:

- transactions were persisted without upload provenance;
- non-null `Ext Txn Id` duplicates were skipped in the importer;
- blank/null `Ext Txn Id` rows were preserved and could repeat;
- alert uniqueness remained one database transaction plus one rule code;
- monitoring evaluated the complete persisted population;
- ML enrichment was one record per database transaction;
- case uniqueness remained one case per alert.

The Phase 5.2 verification found no safe composite identity for blank external
IDs. Candidate fields such as customer/card, date, amount, transaction type,
currency, RRN, and authorization code are nullable, and combinations can
legitimately repeat. A guessed fingerprint would risk silently discarding real
transactions.

## 3. New import/batch model

A minimal `TransactionImport` model was added with:

- `id`
- `source_filename`
- `status`
- `rows_processed`
- `imported_count`
- `duplicate_count`
- `created_at`

Each accepted transaction now stores a nullable `import_id` foreign key to its
originating `TransactionImport` record.

This is provenance only. It is not a workflow engine, does not alter
monitoring scope, and does not make files independent batches.

Existing transactions remain compatible because `import_id` is nullable.
Existing databases receive the column and index through the existing startup
schema-compatibility approach. Existing transaction, alert, ML, case, and
frontend APIs continue to use their existing transaction IDs and response
shapes.

## 4. Deduplication strategy

The hardening preserves the existing defensible identity:

```text
non-null Ext Txn Id
```

The importer skips a row when its non-null external ID already exists in the
database or was already accepted earlier in the same upload.

The importer now reports:

- rows processed;
- records imported;
- duplicates skipped;
- import ID;
- source filename;
- final status.

No database uniqueness constraint was added to `ext_txn_id`, because changing
the schema to enforce uniqueness would create migration and source-system
compatibility risk without addressing null values.

## 5. Why the chosen transaction identity is defensible

`Ext Txn Id` is the source-provided transaction identifier already used by the
existing importer for repeat-upload suppression. It is the only available
field with an explicit transaction-identity role in the current import
contract.

The other inspected fields do not provide a safe universal identity:

- customer/card identifiers identify participants, not individual events;
- transaction date and amount can repeat;
- transaction type and currency can repeat;
- RRN and authorization code can be absent or reused depending on source
  behavior;
- corporate and other-party fields describe participants, not an event key.

Therefore the implementation does not manufacture a fingerprint from those
fields.

## 6. Blank `Ext Txn Id` handling

Blank/null external IDs are intentionally **not deduplicated**.

They are accepted, associated with the current import record, and reported as
imported rows rather than being silently discarded. `duplicates_skipped`
counts only rows skipped by the known non-null external-ID identity.

This preserves data rather than risking false deduplication. The limitation
remains visible and documented:

- repeated blank-ID logical rows can still create multiple database
  transactions;
- each database transaction can have its own alert;
- a future source-specific identity or quarantine policy is required for
  stronger idempotency.

## 7. Import API changes

`POST /transactions/import` retains the existing response field:

```json
{
  "message": "Transactions imported successfully",
  "records_imported": 1
}
```

It now adds:

```json
{
  "import_id": 1,
  "source_filename": "file-a.csv",
  "rows_processed": 1,
  "duplicates_skipped": 0,
  "status": "COMPLETED"
}
```

The direct service function remains backward compatible for existing callers:
it continues returning an integer by default. A detailed result is available
to the upload route without changing existing service-call expectations.

Temporary upload files are still removed in the API `finally` block.

## 8. Monitoring behavior

Monitoring was not redesigned and remains persistent-population based:

- all persisted transactions are evaluated;
- historical transactions remain available;
- rules continue to own deterministic alerts;
- import identity records where transactions originated;
- monitoring is not incremental-only;
- monitoring does not yet attach a monitoring-run record to an import.

No R001-R016 rule semantics or evaluation order changed.

## 9. ML compatibility

The existing ML service and Isolation Forest artifact were not changed.

Verification confirmed:

- an existing customer/card in a later upload still uses prior persisted
  history;
- a brand-new customer/card retains `INSUFFICIENT_HISTORY`;
- no score or anomaly flag is fabricated for insufficient history;
- repeated non-null-ID uploads create no second transaction;
- therefore skipped duplicate rows create no second ML enrichment;
- the existing transaction enrichment API remains compatible;
- enrichment remains one record per persisted transaction.

Import provenance is additive and does not enter the feature pipeline.

## 10. Alert/case compatibility

Existing alert identity remains:

```text
one database transaction + one rule code -> at most one alert
```

Repeated uploads with known non-null IDs do not create new transactions, so
they do not create additional logical alerts or enrichment records.

Existing alert-to-transaction relationships remain intact. Case uniqueness and
case status behavior were not changed. Existing cases remain readable and
duplicate case creation remains rejected by the existing alert-based case
constraint.

Blank-ID rows remain a documented limitation: if the same logical source event
is inserted as separate database transactions, alert identity cannot recognize
those rows as duplicates.

## 11. Tests

Added focused isolated tests in
[test_multi_file_hardening.py](../tests/test_multi_file_hardening.py) covering:

1. valid uploads receive import IDs;
2. different files receive different import IDs;
3. transactions retain import provenance;
4. non-null external-ID duplicates are skipped;
5. import results report imported and duplicate counts;
6. blank-ID rows are not falsely deduplicated;
7. alert idempotency remains intact;
8. ML enrichment is not duplicated for skipped transactions;
9. existing customer history works across uploads;
10. new-customer cold-start behavior remains intact.

Focused Phase 5.2A matrix:

```text
41 passed, 5 existing pandas date-format warnings
```

The matrix included:

- multi-file hardening;
- transaction/import tests;
- alert/monitoring tests;
- ML enrichment tests;
- LLM tests;
- case tests.

Complete backend suite:

```text
122 passed, 5 existing pandas date-format warnings
```

No test framework or package was added.

## 12. Real CSV verification

One isolated in-memory SQLite verification used the supplied development CSV.

| Measure | Result |
|---|---:|
| Import ID | 1 |
| Source rows processed | 15,034 |
| Transactions imported | 15,034 |
| Duplicates skipped | 0 |
| Persisted transactions | 15,034 |
| Deterministic alerts | 6,144 |
| R001 | 6 |
| R002 | 4 |
| R003 | 6,124 |
| R015 | 10 |
| ML enrichment records | 15,034 |

The original deterministic baseline is unchanged.

## 13. Limitations

### Blank external IDs remain non-idempotent

This is intentional because no defensible identity could be established from
the current schema. The next safe step requires a source-system contract,
not an arbitrary database fingerprint.

### Monitoring remains full-population

Adding import identity does not change monitoring cost or scope. Every run
still scans persisted transactions. This is acceptable for the current
architecture and demo, but should be addressed separately for production
scale.

### Existing rows have null import provenance

Transactions created before this hardening cannot be reliably assigned to a
historical source file. They remain readable and compatible.

## 14. Future incremental-monitoring recommendation

Do not switch to incremental-only monitoring as part of this change.

A future phase should define:

1. monitoring-run records and status;
2. explicit run-to-import association;
3. how historical rules use prior transactions while only new alerts are
   emitted;
4. how ML recalculation and model-version changes are handled;
5. replay, failure, and audit semantics.

That design must preserve the current deterministic alert ownership and ML
cold-start policy.

## 15. Interview-ready explanation

The production-hardening change adds a small persistent import record and links
new transactions to it, so the system can answer which upload produced a
transaction. It keeps the existing source-provided `Ext Txn Id` as the only
deduplication key because the other available fields are not guaranteed to
identify one event. Repeated known-ID uploads are reported as duplicates and
do not create new transactions, alerts, or ML records. Blank-ID rows are
preserved rather than incorrectly collapsed, and that limitation is explicit.

Monitoring still evaluates the complete persistent transaction population.
Import identity improves provenance without changing rule semantics, ML
features, alert ownership, case behavior, or frontend contracts.

## Final status

- **Files created:**
  - [transaction_import.py](../backend/app/models/transaction_import.py)
  - [test_multi_file_hardening.py](../tests/test_multi_file_hardening.py)
  - [PHASE_5_2A_MULTI_FILE_HARDENING_REPORT.md](./PHASE_5_2A_MULTI_FILE_HARDENING_REPORT.md)
- **Files modified:**
  - [transaction.py](../backend/app/models/transaction.py)
  - [transaction_service.py](../backend/app/services/transaction_service.py)
  - [transactions.py](../backend/app/api/transactions.py)
  - [database.py](../backend/app/core/database.py)
  - [main.py](../backend/app/main.py)
- **Packages installed:** none
- **Import/batch model added:** yes; minimal `TransactionImport` provenance record
- **Transaction identity strategy:** non-null source `Ext Txn Id`
- **Duplicate handling:** known non-null IDs are skipped and counted; blank IDs are preserved and not falsely deduplicated
- **Tests/results:** focused matrix 41 passed; complete backend suite 122 passed
- **Original baseline:** 15,034 transactions; R001=6, R002=4, R003=6,124, R015=10; total alerts=6,144
- **Rule engine changed:** no
- **ML scoring changed:** no
- **LLM changed:** no
- **Frontend changed:** no
