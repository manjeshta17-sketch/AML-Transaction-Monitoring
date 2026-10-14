# Phase 5.2 — New File / Multi-File Processing Verification Report

## 1. Objective

This verification determines what the current application does when a client
uploads a different transaction file after the existing development data. It
tests import persistence, repeated uploads, new and existing customers/cards,
deterministic monitoring, ML history behavior, and validation without changing
application code.

All synthetic verification used isolated in-memory SQLite databases. The
normal development database and raw source datasets were not modified.

## 2. Current import architecture

The existing importer:

- reads pipe-delimited CSV reports after two metadata rows;
- requires the columns listed by `REQUIRED_COLUMNS`;
- selects known fields and ignores unexpected columns;
- coerces invalid numeric/date values to SQL `NULL`;
- checks existing non-null `Ext Txn Id` values;
- skips duplicate non-null external IDs already in the database or repeated
  within the same file;
- bulk-inserts accepted rows and commits them;
- returns the number of newly inserted rows.

The transaction model has no batch ID, file ID, upload ID, import-run table, or
natural database uniqueness constraint on `ext_txn_id`.

The existing monitoring service queries all persisted transactions with:

```python
db.query(Transaction).order_by(Transaction.id).all()
```

It evaluates the full population, creates deterministic alerts, commits those
results, and then enriches the same full population with ML.

## 3. File A behavior

Synthetic File A contained:

- six historical POS transactions for `customer-a` / `card-a`;
- one high-value LOAD transaction for the same customer/card.

Observed results:

| Result | Value |
|---|---:|
| Imported transactions | 7 |
| Transactions evaluated | 7 |
| Alerts generated | 1 |
| Alert rule | R001 |
| Enrichment records | 7 |
| Available enrichments | 2 |
| Insufficient-history enrichments | 5 |
| Anomaly flags | 1 |

The high-value LOAD created the expected deterministic R001 alert. ML
enrichment did not create any alert.

## 4. File B behavior

Synthetic File B contained:

- one additional POS transaction for the existing `customer-a` / `card-a`;
- one high-value LOAD transaction for new `customer-b` / `card-b`.

File B added two transactions to the same database.

Observed results after importing File B and running monitoring:

| Result | Value |
|---|---:|
| File B imported | 2 |
| Total persisted transactions | 9 |
| Transactions evaluated | 9 |
| New alerts generated | 1 |
| Total alerts | 2 |
| Total enrichment records | 9 |
| Available enrichments | 3 |
| Insufficient-history enrichments | 6 |
| Anomaly flags | 1 |

The new alert was R001 for the File B high-value LOAD. The original File A
alert remained present and was not duplicated.

The existing-customer File B transaction received `AVAILABLE` enrichment. The
new-customer File B transaction received:

```text
anomaly_score = null
anomaly_flag = null
history_sufficient = false
enrichment_status = INSUFFICIENT_HISTORY
```

## 5. Repeated upload behavior

The same logical File B was imported a second time.

Observed results:

| Result | Value |
|---|---:|
| Second File B rows imported | 0 |
| Persisted transaction count after repeat | 9 |
| Alerts generated on repeat monitoring | 0 |
| Total alerts after repeat | 2 |
| Enrichment records after repeat | 9 |

For non-null, repeated `Ext Txn Id` values, the importer is effectively
idempotent. Alert deduplication also prevents duplicate alerts for the same
persisted transaction/rule pair. ML enrichment is upserted by
`transaction_id`, so it is not duplicated.

This is not a complete business-key idempotency guarantee because
`ext_txn_id` is nullable and is not protected by a database uniqueness
constraint. A repeated file with blank external IDs inserted both rows again
on each upload:

```text
first blank-ID upload: 2 rows
second blank-ID upload: 2 rows
blank-ID transactions present afterward: 4
```

Those rows have different database transaction IDs. If they trigger the same
rule, they can also produce separate alerts because alert uniqueness is based
on `(transaction_id, rule_code)`, not the logical source record.

## 6. New customer/card behavior

The File B `customer-b` / `card-b` LOAD had no prior customer or card history.
It still participated in deterministic monitoring and triggered R001 because
R001 depends on the current transaction type and amount, not historical
history.

Its ML record remained explicitly insufficient-history with null score and
flag. No historical information was invented.

This is distinct from a new file containing an existing customer/card:

- **New customer/card:** no prior persisted history; ML remains cold-start.
- **Existing customer/card in new file:** prior persisted transactions are
  available to rules and the ML feature pipeline.

## 7. Existing customer/card behavior

An isolated test created six prior transactions for `customer-a` / `card-a`
and then imported a new transaction for that same customer/card.

The new transaction's stored ML evidence showed:

```text
customer_history_count = 6
card_history_count = 6
customer_mean_amount = 52.5
card_mean_amount = 52.5
customer_velocity_24h = 6
card_velocity_24h = 6
history_sufficient = true
enrichment_status = AVAILABLE
```

Therefore File B transactions for an existing customer/card use prior
transactions already persisted from File A.

## 8. Historical rule behavior

To verify cross-file rule history, File A contained three successful
transactions at the same merchant within one hour. File B contained a fourth
successful transaction at that merchant in the same window.

Observed result:

```text
File A alerts: {}
File B monitoring: 1 new R003 alert
Total evaluated by File B monitoring run: 4
```

The R003 alert was created for the File B transaction. This proves the current
windowed rule evaluation sees File A transactions when evaluating File B.

The monitoring implementation also passes the full persisted population to the
historical rule evaluation path; it is not limited to the latest file.

## 9. ML history behavior

Synthetic ML results were:

### Brand-new customer/card

| Measure | Result |
|---|---:|
| Transactions in scenario | 1 new transaction |
| Sufficient-history records | 0 |
| Insufficient-history records | 1 |
| Anomaly flags | 0 |
| Prior transactions used | none |

### Existing customer/card with additional transaction

| Measure | Result |
|---|---:|
| Prior transactions | 6 |
| New transaction | 1 |
| Sufficient-history records | 1 for the new transaction |
| Insufficient-history records | 0 for the new transaction |
| Anomaly score | present |
| Anomaly flag | present |
| Prior transactions used | yes; six customer/card observations |

Anomaly flags remain unusual-behavior indicators only. They are not fraud or
AML determinations.

## 10. Import validation behavior

### Valid schema

A valid pipe-delimited report with two metadata rows imported successfully and
returned the accepted row count.

### Missing required columns

A report containing only a subset of required columns raised:

```text
ValueError: Transaction CSV is missing required columns: ...
```

No import was completed for that invalid schema.

### Malformed transaction values

A valid-schema report with an invalid amount and invalid transaction date was
accepted as one row. The importer converted:

```text
amount -> NULL
txn_date -> NULL
```

This is the existing defensive normalization behavior. The row remains
persisted, but downstream rules that require those values cannot use them.
Existing pandas date-format warnings were observed.

## 11. Exact architecture classification

The current system is **Model B**:

> All uploaded transactions become one persistent transaction population and
> monitoring reevaluates that population.

It is not Model A because uploads are not independent isolated batches. It is
not Model C because monitoring does not limit evaluation to only newly
imported transactions.

Implications:

- File A transactions remain after File B;
- File B rules can use File A history;
- ML features can use prior persisted customer/card transactions;
- every monitoring run scans the full persisted population;
- deterministic alert creation prevents duplicates for an existing
  transaction/rule pair;
- repeat uploads with non-null external IDs insert no duplicate rows;
- blank external IDs can be inserted repeatedly;
- there is no built-in file/batch identity for separating results by upload.

## 12. Duplicate-alert implications

For repeated non-null `Ext Txn Id` values:

- duplicate transactions were not inserted;
- duplicate alerts were not created;
- enrichment rows were not duplicated;
- repeat monitoring generated zero new alerts.

For duplicate rows lacking `Ext Txn Id`:

- duplicate transactions are possible;
- each duplicate receives a new database ID;
- alert uniqueness does not recognize them as the same source record;
- duplicate logical alerts are therefore possible if both rows trigger a rule.

## 13. Production gaps

### Blank external IDs can defeat import idempotency

**Classification:** PRODUCTION GAP  

**Current behavior:** Rows with null/blank `Ext Txn Id` are inserted on every
upload. The database has no natural transaction uniqueness constraint.

**Why it matters:** Repeated files can grow the transaction population and may
create duplicate logical alerts for rows that lack a source identifier.

**Minimal future change:** Define and validate a business idempotency key
composed from trusted source fields, or reject/route rows without a usable
source identifier. Add an explicit uniqueness policy only after confirming the
source system's contract.

### No batch/file identifier

**Classification:** PRODUCTION GAP  

**Current behavior:** Transactions, alerts, and enrichments do not record the
originating file, upload, or monitoring run.

**Why it matters:** Analysts and operations cannot directly distinguish File A
results from File B results through persisted metadata.

**Minimal future change:** Add an import-batch/run record and foreign-key
references, with retention and replay semantics defined explicitly.

### Full-population rescanning

**Classification:** ACCEPTABLE FOR CURRENT DEMO; PRODUCTION GAP AT SCALE  

**Current behavior:** Every monitoring run evaluates and enriches all persisted
transactions. Existing alert deduplication prevents repeated alert rows, but
work is repeated.

**Why it matters:** Runtime and operational cost grow with the entire database,
and reruns can update enrichment timestamps for older transactions.

**Minimal future change:** Introduce explicit monitoring-run scope and
incremental processing only after preserving the existing deterministic and
historical semantics.

No bug or limitation was hidden, and no redesign was implemented in Phase 5.2.

## 14. Recommended future changes

1. Define an explicit import batch/file identity.
2. Define a source-record idempotency contract for missing external IDs.
3. Add monitoring-run scope and audit records.
4. Separate full historical feature calculation from incremental scoring only
   after validating equivalent rule and ML results.
5. Add operational reporting by batch/run.
6. Preserve current R001-R016 authority and ML cold-start semantics during any
   future redesign.

## 15. Tests and results

Targeted synthetic verification completed successfully:

- File A import and monitoring;
- File B import and monitoring;
- repeated File B upload;
- blank external-ID repeat behavior;
- new customer/card cold start;
- existing customer/card history reuse;
- cross-file R003 historical behavior;
- missing required columns;
- malformed numeric/date values.

Relevant regression tests:

```text
ML + alert monitoring + case tests: 18 passed, 2 existing warnings
```

Complete backend suite:

```text
116 passed, 2 existing warnings
```

Warnings were the existing pandas date-format warnings from transaction
import.

## 16. Application-code change status

No application code was changed. This phase added only this verification
report.

## 17. Interview-ready explanation

**What happens when a different file is uploaded?**  
Its valid, non-duplicate transactions are appended to the persistent
transaction population. The next monitoring run evaluates all persisted
transactions, not only the new file. Existing alerts are retained and alert
deduplication prevents repeated rows for the same transaction/rule identity.

**Does a new file get isolated as a batch?**  
No. The current architecture is Model B: persistent population plus full
rescanning. There is currently no file or monitoring-run identifier.

**Can File B use File A history?**  
Yes. Deterministic windowed rules and ML behavioral features use persisted
transactions. A fourth same-merchant transaction in File B triggered R003
because three qualifying transactions were in File A.

**What happens for a new client?**  
Current-data rules such as R001 can still trigger. ML does not fabricate a
score; the transaction is recorded as insufficient history.

**What happens when the same file is uploaded twice?**  
Rows with non-null external IDs are skipped on the second upload, so no
duplicate transactions, alerts, or enrichment rows are created. Blank external
IDs are a production gap and can be inserted repeatedly.

## Final status

- **Files created:** [PHASE_5_2_MULTI_FILE_VERIFICATION_REPORT.md](./PHASE_5_2_MULTI_FILE_VERIFICATION_REPORT.md)
- **Files modified:** none
- **Packages installed:** none
- **Tests/results:** targeted synthetic verification completed; 18 relevant regression tests passed; full suite 116 passed
- **Duplicate transactions possible:** yes, when `Ext Txn Id` is blank/null
- **Duplicate alerts possible:** yes for duplicated blank-ID source rows that trigger a rule; no for repeated non-null external IDs
- **Historical data retained:** yes, all accepted transactions persist
- **New customers receive ML scores:** no, not until minimum history exists
- **Existing customers use prior history:** yes
- **Architecture:** Model B, persistent-population-based full monitoring
- **Rule files changed:** no
- **ML scoring changed:** no
- **LLM code changed:** no
