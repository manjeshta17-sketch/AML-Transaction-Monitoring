# Phase 3.1 — UI/UX and Existing Workflow Mapping

## Scope and status

This document is the discovery and architecture report for Phase 3.1. It is
based on the completed Phase 2 checkpoint, the current FastAPI routes,
schemas, services, and the accessible case-management view of the Oxygen
reference environment.

No frontend has been created and no production backend, AML rule, import,
alert, case, dashboard, or raw dataset behavior has been changed.

The Phase 2 baseline remains the source of truth:

- 15,034 transactions
- 6,144 alerts
- R001 = 6, R002 = 4, R003 = 6,124, R015 = 10
- 99 tests passed, with 0 failures and 0 skipped

## 1. Existing backend API map

All endpoints below are currently available from the FastAPI application.
Pagination uses `page` and `page_size` with a maximum page size of 100 unless
noted otherwise. API errors use the standard `{ "error": { "code", "message",
"details" } }` envelope.

### System

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/` | API availability/basic metadata |
| GET | `/health` | Health indicator and deployment diagnostics |

### Transactions

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/transactions` | Search, filter, sort, and paginate transactions |
| GET | `/transactions/{transaction_id}` | Transaction detail plus related alert and case summaries |
| POST | `/transactions/import` | Upload and import a pipe-delimited report; returns records imported |

`GET /transactions` supports search across transaction identifiers, customer,
card, RRN, authorization code, and corporate name. It also supports exact
filters for transaction type, status, customer, card, corporate name, currency,
date range, amount range, and sorting by ID, date, amount, type, status,
customer, or external transaction ID.

The import route accepts a file and performs the existing importer behavior,
including temporary-file cleanup. It is an import operation, not a preview or
asynchronous job API.

### Alerts

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/alerts` | Search, filter, sort, and paginate alerts |
| GET | `/alerts/{alert_id}` | Alert detail and bounded source-transaction summary; numeric ID or alert code |
| PATCH | `/alerts/{alert_id}/status` | Set `OPEN`, `IN_PROGRESS`, or `CLOSED` |
| PATCH | `/alerts/{alert_id}/priority` | Set priority 1–4 |
| PATCH | `/alerts/{alert_id}/assignment` | Assign or clear a free-text analyst identifier |
| POST | `/alerts/{alert_id}/case` | Create the single case associated with an alert |

Alert filtering supports status, rule code, priority, assignment, transaction
ID, customer ID, search, created-date range, and sorting by ID, created date,
updated date, priority, status, or rule code.

### Cases

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/cases` | Search, filter, sort, and paginate cases |
| GET | `/cases/{case_id}` | Case workflow data, related alert, transaction, and comments |
| PATCH | `/cases/{case_id}/status` | Apply supported case lifecycle transition |
| PATCH | `/cases/{case_id}/priority` | Set priority 1–4 |
| PATCH | `/cases/{case_id}/assignment` | Assign or clear analyst identifier |
| POST | `/cases/{case_id}/comments` | Add an investigation comment |
| GET | `/cases/{case_id}/comments` | List comments |

Supported case statuses are `OPEN`, `IN_PROGRESS`, and `CLOSED`. Case search
includes case code, case ID, alert ID/code, rule code, transaction ID, and
customer ID. Case list filters include status, priority, assignment, alert
ID, date range, and sorting.

### Rules

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/rules` | List persisted R001–R016 configurations |
| GET | `/rules/{rule_code}` | Retrieve one configuration |
| PATCH | `/rules/{rule_code}` | Update enabled state, risk, priority, or validated parameters |

Rule updates are constrained by the backend. Unknown rule codes and unsupported
parameters are rejected, so the UI must render controls from the returned
configuration and not assume arbitrary rule creation.

### Dashboard

| Method | Path | Frontend use |
| --- | --- | --- |
| GET | `/dashboard/summary` | Transaction, alert, and case KPI cards |
| GET | `/dashboard/alerts/trend` | Alert trend chart |
| GET | `/dashboard/transactions/trend` | Transaction trend chart |
| GET | `/dashboard/rules/top` | Top alert-generating rules |
| GET | `/dashboard/distributions` | Alert risk/priority and case priority distributions |

Summary and trends support `24h`, `7d`, or `30d`, or a custom date range.
Summary includes transaction totals and amounts, alert totals/open/closed and
breakdowns, case totals/status/priority/assignment breakdowns, and high
priority alert/case counts. The backend does not expose a separate recent-alert
feed; the alerts list should be used for that view.

### Monitoring

| Method | Path | Frontend use |
| --- | --- | --- |
| POST | `/monitoring/run` | Run enabled rules and persist new alerts |

The response includes transactions evaluated, new alerts generated, counts by
rule, insufficient-history diagnostics, and data-insufficient diagnostics.
Repeated runs are idempotent. The UI must distinguish a completed run from a
new-alert count of zero.

## 2. Oxygen/reference workflow findings

The accessible `/cases` view confirms the following operational patterns. This
is workflow reference only; it is not a source for branding, assets, source
code, or exact visual replication:

- A dedicated Case Management page with a clear page title and supporting text.
- A prominent search field labeled “Search By Title”.
- Status and priority selectors with an all-values option.
- A case table with case ID, title, alert ID, status, priority, assignment,
  created date, and an action column.
- A loading state while case data is fetched.
- A visible create-case action.
- User/session controls in the application chrome.

Only these observations are confirmed from the accessible reference page.
Features such as advanced bulk actions, saved searches, audit history,
notifications, or analyst directories must not be treated as existing Oxygen
requirements without further evidence.

The proposed application should preserve the useful operational concepts:
searchable work queues, explicit status/priority, assignment, relationship
navigation, investigation comments, and a predictable detail-to-action flow.
It should use its own restrained visual language and information hierarchy.

## 3. Confirmed features, reference concepts, and proposed enhancements

### Confirmed by this backend

- Transaction import, search, filtering, pagination, sorting, and detail.
- Alert list/detail, status, priority, assignment, and one-case creation.
- Case list/detail, lifecycle status, priority, assignment, and comments.
- Persistent configuration for R001–R016 with validated updates.
- Monitoring execution with idempotent alert persistence and diagnostics.
- Dashboard summary, trends, rule counts, and distributions.
- Standard error responses and OpenAPI documentation.

### Observed from the reference workflow

- Case-management work queue with search and compact operational table.
- Status/priority filtering.
- Clear create-case affordance.
- Loading feedback and authenticated-application chrome.

### Proposed enhancements for the frontend

- Shared application shell with navigation and consistent filter/toolbars.
- Linked navigation: transaction → alert → case and case → alert → transaction.
- URL-persisted filters and pagination for analyst handoff/bookmarking.
- Explicit loading, empty, validation-error, and retry states.
- Read-only explanation of rule configuration and monitoring diagnostics.
- A reports experience built from existing dashboard endpoints.

These proposed enhancements do not imply new backend capability.

## 4. Frontend-supported analyst operations

The first frontend can support the following without backend changes:

1. Load dashboard KPIs, trends, distributions, and top rules.
2. Search/filter/sort/paginate transactions, alerts, and cases.
3. Open transaction, alert, and case details.
4. Update alert status, priority, and assignment.
5. Create a case from an alert, handling the existing-case conflict.
6. Update case status, priority, and assignment.
7. Add and view case comments.
8. View and edit the backend-provided rule configuration fields.
9. Upload a report and show the import response.
10. Start monitoring and show the completed run result and diagnostics.

## 5. Operations requiring future backend work

These should be planned, not faked in Phase 3.1:

| Need | Current gap | Recommended future API |
| --- | --- | --- |
| Validate before import | Import is immediate; no dry-run/preview response | `POST /transactions/validate` returning metadata, detected columns, row counts, and row-level errors |
| Import progress/status | Import and monitoring are synchronous responses | A job endpoint such as `POST /processing/imports` plus `GET /processing/{job_id}` |
| Processing history | No persisted file/run record | File-processing run resource with filename, timestamps, counts, state, and errors |
| Monitoring progress | Only completed `POST /monitoring/run` response exists | Job/status endpoint if runs become long-running |
| Alert-to-case on alert detail | Alert detail has source transaction but no case summary | Include case relationship in alert detail or add a relationship endpoint |
| Case title | Case schema has code/status/priority but no title field | Add a defined title contract before exposing title editing/search as a first-class field |
| Analyst directory | Assignment is a free-text identifier | Analyst/team lookup endpoint and authorization model |
| Dedicated recent alerts | No recent-alert dashboard endpoint | Add a bounded recent-alert endpoint if list-query reuse is insufficient |
| Audit trail | No audit-event endpoint/model in the current API | Immutable audit events for workflow/configuration changes |
| Report-specific aggregates | Dashboard has useful aggregate primitives but no case opened/closed trend or transaction-status distribution | Add explicit report endpoints only when a measurable report requirement is approved |

For Phase 3, the UI should use an import-result page and a monitoring-result
panel rather than showing unsupported progress or validation stages.

## 6. Proposed information architecture

### Primary navigation

1. **Dashboard** — operational overview and prioritization.
2. **Transactions** — searchable source activity and transaction context.
3. **Alerts** — detection work queue and alert-to-case entry point.
4. **Cases** — investigation work queue and case lifecycle.
5. **Rules** — governed R001–R016 configuration.
6. **File Processing** — upload/import and monitoring actions, with clear
   labeling of the current synchronous capabilities.
7. **Reports** — reusable analytical views built from real dashboard data.

System health can live in a small shell status affordance or diagnostics
drawer; it does not need a primary navigation item.

### Global shell

- Left navigation on desktop and collapsible navigation on smaller screens.
- Header with page title, selected date scope where applicable, health state,
  and user/session placeholder.
- Consistent content width, table density, badge semantics, and action placement.
- Breadcrumbs or contextual links on detail pages.
- No decorative metric cards that do not map to an API field.

## 7. Page and UX designs

### Dashboard

Top row:

- Total transactions
- Transaction amount
- Total alerts
- Open alerts
- High-priority alerts
- Total cases
- Open/in-progress/closed case counts

Use the selected `24h`, `7d`, `30d`, or custom range consistently across
summary and trend calls. Recommended visual structure:

- Alert and transaction trend as the primary chart area.
- Top alert-generating rules as a ranked horizontal bar/table.
- Alert risk/priority and case priority as compact distributions.
- A recent-alert table implemented by querying `/alerts` with descending
  creation time; label it as a work queue, not a separate dashboard metric.

Avoid derived “percent change”, SLA, investigator productivity, or exposure
metrics until the backend supplies definitions. Empty datasets should display
“No data for this range”, not zero-valued fake activity.

### Transactions

List toolbar:

- Search
- Date range
- Transaction type
- Status
- Customer ID
- Card number
- Corporate name
- Currency
- Amount min/max
- Sort and page size

Table columns should prioritize date, external transaction ID, customer,
transaction type, amount/currency, status, and alert indicator. Preserve
backend pagination metadata and show the current result count.

Detail sections:

- Transaction identity and timestamp
- Customer/card/corporate context
- Amount, currency, fees, balance, type, status, and descriptive fields
- Source/reference fields when present
- Related alerts and related cases from the detail response

Every related alert/case row should link to its detail route, creating the
transaction → alert → case path without duplicating domain logic.

### Alerts

List toolbar:

- Search
- Status
- Rule
- Priority
- Assignment
- Customer/transaction filters
- Created-date range
- Sort and pagination

Table columns:

- Alert code
- Rule code/name
- Risk and priority
- Transaction ID/customer
- Status
- Assigned analyst
- Created/updated time
- Case indicator/action

Alert detail:

- Alert identity, rule explanation, risk, priority, status, assignment
- Source transaction summary with a link
- Relevant detection description/metadata returned by the API
- Action controls for status, priority, assignment, and create-case

The case action should be disabled or replaced with a relationship link after
the backend reports an existing-case conflict. Do not infer case existence
from a list count that may be stale.

### Cases

List toolbar:

- Search
- Status
- Priority
- Assignment
- Alert ID
- Created-date range
- Sort and pagination

Table columns:

- Case code
- Alert ID/code
- Rule
- Status
- Priority
- Assigned analyst
- Created/updated time
- Action

Case detail:

- Case identity and lifecycle state
- Related alert and transaction context
- Priority and assignment controls
- Comment timeline, author, and timestamp
- Add-comment form with validation and optimistic-free refresh

Use explicit transition controls and show backend transition errors. “Close
case” is a status transition, not a separate invented endpoint.

### Rules

Rules list columns:

- Rule code/name
- Category
- Enabled state
- Risk level
- Priority
- Updated time

Rule detail should render editable fields from `parameters`, with friendly
labels and type-aware controls for values returned by the backend. The
frontend may provide descriptions for known parameter keys, but submitted
values must remain backend-validated. Show a save/reload state and the exact
validation error returned by the API.

Do not show an “Add Rule” button. Rule creation is not supported. R004 and
other data-insufficient/disabled configurations should be presented honestly
using their persisted state and description.

### File Processing

Current page flow:

1. Select a supported report file.
2. Submit to `/transactions/import`.
3. Show success with records imported or the standard error.
4. Offer “Run monitoring” using `/monitoring/run`.
5. Show evaluated count, new alerts by rule, and insufficient-data/history
   diagnostics.

The UI must not claim that preview, validation-before-import, progress, or
processing history exists. A future staged workflow can add those states once
the APIs in Section 5 are implemented.

### Reports

Phase 3 reports can reuse:

- Summary KPIs from `/dashboard/summary`
- Alert/transaction trends
- Top rules
- Risk/priority distributions
- Cases by status from summary
- Transaction types from summary

Provide date-range controls, charts with accessible tabular alternatives, and
CSV export only if a backend or client-side export contract is approved. Do
not call this Power BI or embed Power BI. A “Power-BI-style” analytical
experience means readable filters, charts, and tables using real API data.

## 8. AML rule-management requirements

Rules R001–R016 remain backend-owned. The frontend should:

- Fetch `/rules` on entry and use the response as the source of truth.
- Show enabled, category, risk, priority, and description.
- Render supported parameter inputs from the rule code and returned parameter
  keys, with type and allowed-field guidance.
- Keep a dirty-state indicator and require an explicit save.
- Refresh the saved response after a successful patch.
- Surface `404`, `422`, and general API errors without silently resetting edits.

Examples of parameter groups include R001 amount threshold, R002/R003
merchant/count/window/status settings, historical lookbacks for R005–R007,
country/currency fields for R008–R012 and R016, and source/domestic settings
for R013–R014. These are UI groupings only; the rule engine and validation
remain unchanged.

## 9. Future AI integration points

AI is Phase 4 or later and must remain advisory:

- Daily monitoring summary generated from completed monitoring results.
- Plain-language alert explanation grounded in the persisted rule and fields.
- Case summary from comments and linked evidence.
- Investigation assistance for finding relevant transaction context.
- Recurring customer-behavior and anomaly exploration.

AI must not alter rule configuration, create/close alerts or cases, or silently
make final AML decisions. Any future AI action should be explicit, auditable,
permission-aware, and clearly separated from deterministic AML outcomes.

## 10. Frontend technology recommendation

- **React + TypeScript** for component safety, API response modeling, and
  maintainable forms/tables.
- A conventional Vite React application is appropriate; it does not replace
  FastAPI and does not introduce another backend.
- Use a small HTTP client wrapper around `fetch` or an established REST query
  library. Centralize error-envelope parsing and query-string serialization.
- Use CSS modules or a restrained application stylesheet/design-token layer.
  Avoid adding a large visual framework solely for decoration.
- Use a charting library only for the required trend/distribution views, with
  tables or accessible summaries as fallbacks.
- Keep domain types aligned to the OpenAPI contract. Do not duplicate rule
  logic, dashboard calculations, or status-transition rules in the frontend.

## 11. Proposed Phase 3 milestones

### 3.1 UI/UX and workflow mapping — this report

Approve information architecture, route map, page states, API contracts,
design principles, and explicit backend gaps.

### 3.2 React application shell

Create the typed frontend foundation, routing, API client, layout, navigation,
shared badges, tables, filter controls, loading/error/empty states, and
responsive foundations. Do not add page-specific business behavior before
the shell contract is stable.

### 3.3 Dashboard

Implement range selection, KPI cards, trends, distributions, top rules, and
the recent-alert work-queue query using existing endpoints.

### 3.4 Transactions

Implement the filterable/paginated list, detail page, related links, and
import entry point where appropriate.

### 3.5 Alerts

Implement the alert work queue, detail view, workflow actions, conflict
handling, and transaction/case navigation.

### 3.6 Cases

Implement the case queue, detail/investigation view, lifecycle actions,
assignment, and comments.

### 3.7 Rules

Implement backend-driven configuration presentation and validated editing;
add focused frontend tests for parameter rendering and error handling.

### 3.8 File Processing

Implement the currently supported upload/import and monitoring-result flow.
Track preview/progress/history as explicitly deferred backend work.

### 3.9 Reports and analytics

Compose reusable dashboard-backed charts and tables, with consistent range
semantics and no unsupported metrics.

### 3.10 Integration and end-to-end verification

Verify OpenAPI response mapping, error states, pagination/filter semantics,
status transitions, alert-to-case idempotency, rule edits, import cleanup,
monitoring idempotency, and the unchanged 99-test backend baseline.

## 12. Risks and architectural concerns

1. **No frontend dependency manifest exists yet.** The frontend should add its
   own conventional manifest only when Phase 3.2 is approved.
2. **SQLite is the current backend database.** Concurrent imports, monitoring,
   and future job processing need an explicit deployment strategy.
3. **Assignment is free text.** A production analyst directory, identity,
   permissions, and audit model will eventually be needed.
4. **Alert detail does not currently expose a case relationship.** The UI must
   handle this as a known gap rather than make a second uncontracted query.
5. **Case title is not in the case schema.** The reference workflow displays a
   title, but the current system should use case code/alert/rule context until
   a title contract is approved.
6. **The synchronous import and monitoring endpoints can block the page.**
   A future job/status API is needed for large production files.
7. **Dashboard ranges use different entity timestamps.** Transactions use
   transaction date, alerts use creation date, and cases use creation date;
   labels should make this clear.
8. **The dataset is one week and contains known data gaps.** The UI must
   distinguish no data, insufficient history, and data-insufficient diagnostics.
9. **No authentication/authorization contract is exposed.** Do not present
   client-side access controls as security until backend identity and
   authorization are defined.
10. **The raw datasets are immutable.** Frontend development and demos must
    not modify or replace them.

## Decision summary

Proceed to Phase 3.2 only after reviewing this report. The first frontend
should be a thin, typed operational client of the existing FastAPI backend,
with no duplicated AML decisions and no invented processing stages or metrics.
