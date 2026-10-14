# Rule status mapping

## Dataset observations

The supplied CSV uses `PAYMENT_SUCCESS` and `REVERSED` in its `Status` field.
It does not contain a literal `DECLINED` status. Some `TransactionType` values
are reversal-labelled (for example `POS_REVERSAL`) and some are decline-fee
labelled; those are separate source concepts.

## R002

R002 counts a transaction when either condition is true:

- `Status` is in the configurable `qualifying_statuses` list, which defaults
  to `DECLINED` and `REVERSED`; or
- `TransactionType` ends in a configurable reversal suffix, defaulting to
  `_REVERSAL`.

`REVERSED` is counted as a reversal outcome, never as a replacement or alias
for `DECLINED`. Decline-fee transaction types are not treated as declined card
purchases without a source-data definition that confirms that interpretation.

R002 groups by configurable `Other Party Id` and uses a backward-looking,
inclusive time window. At exactly one hour apart, transactions are in the same
window. A trigger is produced for each transaction that raises the merchant's
in-window count above the configured threshold.

## R003

R003 counts only configured successful statuses, defaulting to
`PAYMENT_SUCCESS`, using the same merchant identifier and inclusive window.

## R004

R004 is defined but disabled with `implementation_status=DATA_INSUFFICIENT`.
Faithful implementation requires a canonical declined outcome, an explicit
card-purchase indicator, and a historical per-card baseline to establish what
is unusual. None is available in the supplied extract, so the rule deliberately
does not generate triggers.

## R005

R005 evaluates `LOAD` transactions grouped by the configured entity, defaulting
to `Card Number`. A current load triggers when its amount is strictly more than
the configured percentage above the average amount of individual loads in the
preceding configured number of calendar months. The default is six months and
100%; an amount exactly 100% above the baseline does not trigger.

## R006

R006 evaluates the current calendar month's total `LOAD` amount against the
average monthly `LOAD` total in the preceding configured number of calendar
months. The default lookback is twelve months and the default increase is 50%.
The current total must be strictly greater than the threshold. A month without
all required prior calendar months produces an insufficient-history result
instead of an alert.

## R007

R007 evaluates the current calendar month's `LOAD` count against the average
monthly `LOAD` count in the preceding configured number of calendar months. The
default lookback is six months and the default increase is 50%. The current
count must be strictly greater than the threshold. Missing prior months produce
an insufficient-history result instead of an alert.

For R005-R007, only `RuleTriggerResult` values are eligible for alert
persistence. `InsufficientHistoryResult` values remain evaluation diagnostics
and are never passed to `AlertService`. Calendar months are normalized to the
first day at midnight, and the real one-week report is not treated as a
six- or twelve-month history.

## R008-R012

The transaction model supports explicit nullable `country_code` and
`home_currency` fields. The supplied report does not provide either field;
its `Currency` column is mapped only to the transaction currency and cannot be
used as a home-currency or country proxy.

R008 and R009 identify POS and ATM transactions from the explicit
`TransactionType` values. They trigger only when the amount is strictly above
the configurable threshold (default `999`) and transaction currency differs
from the explicit home currency. Missing home currency produces a
`DataInsufficientResult`, not an alert.

R010 and R011 use explicit POS/ATM types and a configurable normalized
high-risk/blocked country-code list. They do not apply the R008/R009 amount
threshold. Missing country data produces a `DataInsufficientResult`.

R012 groups by the configurable card identifier (default `card_number`) and
compares explicit country codes within an inclusive configurable time window
(default 12 hours). A later transaction triggers when it has a different
country code from an earlier transaction on the same card. Missing card,
country, or timestamp data produces a `DataInsufficientResult`.

Data-insufficient results are diagnostics only. They are returned by the rule
evaluation and monitoring response, but only normal `RuleTriggerResult` values
are passed to `AlertService`.

## R013

R013 identifies ATM activity from the explicit `TransactionType == "ATM"`
value. It groups by the configured card or customer field, counts explicit
domestic ATM transactions per calendar month, and compares the latest observed
month with the average count over the configured prior months. The default
lookback is six months and the default increase is 50%. Domestic status must
come from the explicit configured field and configured domestic values;
currency is never used as a domestic proxy. “Current month” means the latest
observed transaction month for each entity in the evaluated input, not the
system's current calendar month.

## R014

R014 groups `LOAD` transactions by the configured card or customer field and
examines the configured calendar-month lookback, defaulting to three months.
Every load in that window must have an explicit configured source whose value
is in the configurable C2C source list. Missing source evidence produces a
`DataInsufficientResult`; unrelated transaction fields and transaction type
alone are not treated as proof of load source.

## R016

R016 compares explicit settlement-currency and originating-country-currency
fields. It triggers when both are present and differ, without deriving either
value from the generic transaction currency, country code, merchant data, or
any other field. Missing explicit fields produce a `DataInsufficientResult`.
