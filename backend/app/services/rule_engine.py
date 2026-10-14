"""Configurable transaction-level AML rule evaluation."""

from collections import deque
from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from backend.app.models.transaction import Transaction
from backend.app.schemas.rule import (
    InsufficientHistoryResult,
    DataInsufficientResult,
    RuleDefinition,
    RuleEvaluationOutcome,
    RuleTriggerResult,
)


AMOUNT_THRESHOLD_PARAMETER = "amount_threshold"
TRANSACTION_TYPE_PARAMETER = "transaction_type"
COUNT_THRESHOLD_PARAMETER = "count_threshold"
TIME_WINDOW_MINUTES_PARAMETER = "time_window_minutes"
MERCHANT_FIELD_PARAMETER = "merchant_field"
QUALIFYING_STATUSES_PARAMETER = "qualifying_statuses"
QUALIFYING_TRANSACTION_TYPE_SUFFIXES_PARAMETER = "qualifying_transaction_type_suffixes"
GROUPING_FIELD_PARAMETER = "grouping_field"
LOOKBACK_MONTHS_PARAMETER = "lookback_months"
INCREASE_PERCENTAGE_PARAMETER = "increase_percentage"
COUNTRY_FIELD_PARAMETER = "country_field"
HOME_CURRENCY_FIELD_PARAMETER = "home_currency_field"
HIGH_RISK_COUNTRIES_PARAMETER = "high_risk_countries"
TIME_WINDOW_HOURS_PARAMETER = "time_window_hours"
DOMESTIC_VALUES_PARAMETER = "domestic_values"
LOAD_SOURCE_PARAMETER = "load_source_field"
C2C_SOURCE_VALUES_PARAMETER = "c2c_source_values"
SETTLEMENT_CURRENCY_PARAMETER = "settlement_currency_field"
ORIGINATING_COUNTRY_CURRENCY_PARAMETER = "originating_country_currency_field"
RULE_CLASSIFICATIONS = {
    "R001": "single_transaction",
    "R002": "merchant_window",
    "R003": "merchant_window",
    "R004": "disabled",
    "R005": "historical",
    "R006": "historical",
    "R007": "historical",
    "R008": "data_dependent",
    "R009": "data_dependent",
    "R010": "data_dependent",
    "R011": "data_dependent",
    "R012": "data_dependent",
    "R013": "data_dependent",
    "R014": "data_dependent",
    "R015": "single_transaction",
    "R016": "data_dependent",
}

WINDOWED_RULE_CODES = {
    code for code, classification in RULE_CLASSIFICATIONS.items()
    if classification == "merchant_window"
}
HISTORICAL_RULE_CODES = {
    code for code, classification in RULE_CLASSIFICATIONS.items()
    if classification == "historical"
}
DATA_INSUFFICIENT_RULE_CODES = {
    code for code, classification in RULE_CLASSIFICATIONS.items()
    if classification == "data_dependent"
}
DATA_RULE_EVALUATORS = {
    "R008": "_evaluate_international_transaction_rule",
    "R009": "_evaluate_international_transaction_rule",
    "R010": "_evaluate_international_transaction_rule",
    "R011": "_evaluate_international_transaction_rule",
    "R012": "_evaluate_different_country_rule",
    "R013": "_evaluate_domestic_atm_rule",
    "R014": "_evaluate_c2c_load_rule",
    "R016": "_evaluate_currency_conversion_rule",
}


DEFAULT_RULES = (
    RuleDefinition(
        rule_code="R001", name="High-value card load",
        description="Detects card loads exceeding the configured amount threshold.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={TRANSACTION_TYPE_PARAMETER: "LOAD", AMOUNT_THRESHOLD_PARAMETER: 5000.0},
    ),
    RuleDefinition(
        rule_code="R002", name="Repeated declined or reversal-related merchant activity",
        description=("Detects more than the configured number of qualifying declined or "
                     "reversal-related transactions at one merchant within the configured window."),
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            MERCHANT_FIELD_PARAMETER: "other_party_id",
            COUNT_THRESHOLD_PARAMETER: 3,
            TIME_WINDOW_MINUTES_PARAMETER: 60,
            # REVERSED is a separate reversal outcome, not an alias for DECLINED.
            QUALIFYING_STATUSES_PARAMETER: ("DECLINED", "REVERSED"),
            QUALIFYING_TRANSACTION_TYPE_SUFFIXES_PARAMETER: ("_REVERSAL",),
        },
    ),
    RuleDefinition(
        rule_code="R003", name="Repeated successful merchant activity",
        description=("Detects more than the configured number of successful transactions "
                     "at one merchant within the configured window."),
        category="transaction_monitoring", risk_level="medium", priority=2,
        parameters={
            MERCHANT_FIELD_PARAMETER: "other_party_id",
            COUNT_THRESHOLD_PARAMETER: 3,
            TIME_WINDOW_MINUTES_PARAMETER: 60,
            QUALIFYING_STATUSES_PARAMETER: ("PAYMENT_SUCCESS",),
        },
    ),
    RuleDefinition(
        rule_code="R004", name="Unusual declined or reversal card purchase activity",
        description=("Defined but disabled: the supplied data lacks a canonical DECLINED "
                     "outcome and the historical/card baseline required to determine unusual activity."),
        category="transaction_monitoring", risk_level="high", priority=1, enabled=False,
        parameters={
            "implementation_status": "DATA_INSUFFICIENT",
            "required_data": "canonical decline outcome, card-purchase indicator, and historical per-card baseline",
            "status_mapping": "REVERSED is not treated as DECLINED",
        },
    ),
    RuleDefinition(
        rule_code="R005", name="Unusual card loading amount",
        description="Current LOAD amount is more than the configured percentage above its historical single-load average.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={GROUPING_FIELD_PARAMETER: "card_number", LOOKBACK_MONTHS_PARAMETER: 6,
                    INCREASE_PERCENTAGE_PARAMETER: 100.0},
    ),
    RuleDefinition(
        rule_code="R006", name="Monthly loading value above historical average",
        description="Current monthly LOAD value is more than the configured percentage above the prior monthly average.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={GROUPING_FIELD_PARAMETER: "card_number", LOOKBACK_MONTHS_PARAMETER: 12,
                    INCREASE_PERCENTAGE_PARAMETER: 50.0},
    ),
    RuleDefinition(
        rule_code="R007", name="Monthly loading frequency above historical average",
        description="Current monthly LOAD count is more than the configured percentage above the prior monthly average.",
        category="transaction_monitoring", risk_level="medium", priority=2,
        parameters={GROUPING_FIELD_PARAMETER: "card_number", LOOKBACK_MONTHS_PARAMETER: 6,
                    INCREASE_PERCENTAGE_PARAMETER: 50.0},
    ),
    RuleDefinition(
        rule_code="R015", name="High-value card-to-card transfer",
        description="Detects card-to-card transfers exceeding the configured amount threshold.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={TRANSACTION_TYPE_PARAMETER: "CARD_TO_CARD", AMOUNT_THRESHOLD_PARAMETER: 1000.0},
    ),
    RuleDefinition(
        rule_code="R008", name="International POS transaction outside home currency",
        description="Detects POS transactions above the threshold whose currency differs from the configured home currency.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            TRANSACTION_TYPE_PARAMETER: "POS",
            AMOUNT_THRESHOLD_PARAMETER: 999.0,
            HOME_CURRENCY_FIELD_PARAMETER: "home_currency",
        },
    ),
    RuleDefinition(
        rule_code="R009", name="International ATM transaction outside home currency",
        description="Detects ATM transactions above the threshold whose currency differs from the configured home currency.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            TRANSACTION_TYPE_PARAMETER: "ATM",
            AMOUNT_THRESHOLD_PARAMETER: 999.0,
            HOME_CURRENCY_FIELD_PARAMETER: "home_currency",
        },
    ),
    RuleDefinition(
        rule_code="R010", name="International POS transaction involving a high-risk country",
        description="Detects POS transactions above the threshold involving a configured high-risk or blocked country.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            TRANSACTION_TYPE_PARAMETER: "POS",
            COUNTRY_FIELD_PARAMETER: "country_code",
            HIGH_RISK_COUNTRIES_PARAMETER: (),
        },
    ),
    RuleDefinition(
        rule_code="R011", name="International ATM transaction involving a high-risk country",
        description="Detects ATM transactions above the threshold involving a configured high-risk or blocked country.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            TRANSACTION_TYPE_PARAMETER: "ATM",
            COUNTRY_FIELD_PARAMETER: "country_code",
            HIGH_RISK_COUNTRIES_PARAMETER: (),
        },
    ),
    RuleDefinition(
        rule_code="R012", name="Different countries on the same card within twelve hours",
        description="Detects two transactions on one card with different country codes inside the configured time window.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            GROUPING_FIELD_PARAMETER: "card_number",
            COUNTRY_FIELD_PARAMETER: "country_code",
            TIME_WINDOW_HOURS_PARAMETER: 12,
        },
    ),
    RuleDefinition(
        rule_code="R013", name="Increased frequency of domestic ATM transactions",
        description="Detects a current month's domestic ATM count above its historical monthly baseline.",
        category="transaction_monitoring", risk_level="medium", priority=2,
        parameters={
            TRANSACTION_TYPE_PARAMETER: "ATM",
            GROUPING_FIELD_PARAMETER: "card_number",
            LOOKBACK_MONTHS_PARAMETER: 6,
            INCREASE_PERCENTAGE_PARAMETER: 50.0,
            "domestic_field": "domestic_status",
            DOMESTIC_VALUES_PARAMETER: ("DOMESTIC",),
        },
    ),
    RuleDefinition(
        rule_code="R014", name="Only source of load is C2C transfer",
        description="Detects entities whose LOAD activity has only an explicitly recorded C2C source in the lookback period.",
        category="transaction_monitoring", risk_level="high", priority=1,
        parameters={
            GROUPING_FIELD_PARAMETER: "card_number",
            LOOKBACK_MONTHS_PARAMETER: 3,
            LOAD_SOURCE_PARAMETER: "load_source",
            C2C_SOURCE_VALUES_PARAMETER: ("C2C",),
        },
    ),
    RuleDefinition(
        rule_code="R016", name="Unusual dynamic currency conversion",
        description="Detects transactions whose settlement currency differs from the originating country's currency.",
        category="transaction_monitoring", risk_level="medium", priority=2,
        parameters={
            SETTLEMENT_CURRENCY_PARAMETER: "settlement_currency",
            ORIGINATING_COUNTRY_CURRENCY_PARAMETER: "originating_country_currency",
        },
    ),
)


class RuleEngine:
    """Evaluates enabled rules without creating or persisting alerts."""

    def __init__(self, rules: Iterable[RuleDefinition] | None = None):
        self.rules = tuple(DEFAULT_RULES if rules is None else rules)

    def evaluate(self, transaction: Transaction) -> list[RuleTriggerResult]:
        """Evaluate rules that require only one transaction."""
        results = [
            self._build_result(transaction, rule)
            for rule in self.rules
            if rule.enabled
            and rule.rule_code not in WINDOWED_RULE_CODES | HISTORICAL_RULE_CODES | DATA_INSUFFICIENT_RULE_CODES
            and self._matches_amount_threshold(transaction, rule)
        ]
        return results

    def evaluate_transactions(self, transactions: Iterable[Transaction]) -> list[RuleTriggerResult]:
        return self.evaluate_with_context(transactions).triggers

    def evaluate_with_context(self, transactions: Iterable[Transaction]) -> RuleEvaluationOutcome:
        """Evaluate single-transaction and merchant-windowed rules.

        Window boundaries are inclusive: events exactly one configured window
        apart are counted together. A result is emitted for each event that
        raises its merchant's trailing count above the configured threshold.
        """
        transaction_list = list(transactions)
        results = [result for transaction in transaction_list for result in self.evaluate(transaction)]
        for rule in self.rules:
            if rule.enabled and RULE_CLASSIFICATIONS.get(rule.rule_code) == "merchant_window":
                results.extend(self._evaluate_merchant_window(transaction_list, rule))
        insufficient_history = []
        data_insufficient = []
        for rule in self.rules:
            if rule.enabled and RULE_CLASSIFICATIONS.get(rule.rule_code) == "historical":
                historical_results, missing_history = self._evaluate_historical_rule(transaction_list, rule)
                results.extend(historical_results)
                insufficient_history.extend(missing_history)
        for rule in self.rules:
            if rule.enabled and RULE_CLASSIFICATIONS.get(rule.rule_code) == "data_dependent":
                evaluator_name = DATA_RULE_EVALUATORS[rule.rule_code]
                evaluator = getattr(self, evaluator_name)
                rule_results, missing_data = evaluator(transaction_list, rule)
                results.extend(rule_results)
                data_insufficient.extend(missing_data)
        return RuleEvaluationOutcome(results, insufficient_history, data_insufficient)

    def _evaluate_domestic_atm_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[DataInsufficientResult]]:
        """Evaluate the latest observed calendar month, not the system's current month."""
        grouping_field = rule.parameters.get(GROUPING_FIELD_PARAMETER)
        lookback = rule.parameters.get(LOOKBACK_MONTHS_PARAMETER)
        increase = rule.parameters.get(INCREASE_PERCENTAGE_PARAMETER)
        domestic_field = rule.parameters.get("domestic_field")
        domestic_values = rule.parameters.get(DOMESTIC_VALUES_PARAMETER)
        if (
            grouping_field not in {"card_number", "customer_id"}
            or not isinstance(lookback, int) or lookback < 1
            or not isinstance(increase, (int, float)) or increase < 0
            or not isinstance(domestic_field, str)
            or not isinstance(domestic_values, (tuple, list, set))
        ):
            raise ValueError(f"Rule {rule.rule_code} has invalid domestic ATM parameters.")

        missing_fields: set[str] = set()
        domestic_set = {str(value).strip().upper() for value in domestic_values}
        groups = self._group_by_entity_and_month(
            transactions,
            grouping_field,
            lambda transaction: transaction.transaction_type
            == rule.parameters.get(TRANSACTION_TYPE_PARAMETER),
            missing_fields,
        )
        if any(
            transaction.transaction_type == rule.parameters.get(TRANSACTION_TYPE_PARAMETER)
            and getattr(transaction, domestic_field, None) in (None, "")
            for transaction in transactions
        ):
            missing_fields.add(domestic_field)

        if domestic_field in missing_fields:
            return [], [
                self._data_insufficient(
                    rule, (str(grouping_field), domestic_field, "txn_date"), missing_fields
                )
            ]

        triggers: list[RuleTriggerResult] = []
        for entity, items in groups.items():
            by_month = items
            months = sorted(by_month)
            if not months:
                continue
            current_month = months[-1]
            historical_months = self._prior_months(current_month, lookback)
            if any(month not in by_month for month in historical_months):
                missing_fields.add(f"{lookback}_months_of_domestic_atm_history")
                continue
            historical_counts = [
                sum(
                    str(getattr(item, domestic_field)).strip().upper() in domestic_set
                    for item in by_month[month]
                    if getattr(item, domestic_field, None) not in (None, "")
                )
                for month in historical_months
            ]
            current_domestic = [
                item for item in by_month[current_month]
                if getattr(item, domestic_field, None) not in (None, "")
                and str(getattr(item, domestic_field)).strip().upper() in domestic_set
            ]
            baseline = sum(historical_counts) / lookback
            if current_domestic and len(current_domestic) > baseline * (1 + increase / 100):
                triggers.append(self._build_result(max(current_domestic, key=self._transaction_sort_key), rule))
        missing = [
            self._data_insufficient(rule, (str(grouping_field), domestic_field, "txn_date"), missing_fields)
        ] if missing_fields else []
        return triggers, missing

    def _evaluate_c2c_load_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[DataInsufficientResult]]:
        grouping_field = rule.parameters.get(GROUPING_FIELD_PARAMETER)
        lookback = rule.parameters.get(LOOKBACK_MONTHS_PARAMETER)
        source_field = rule.parameters.get(LOAD_SOURCE_PARAMETER)
        source_values = rule.parameters.get(C2C_SOURCE_VALUES_PARAMETER)
        if (
            grouping_field not in {"card_number", "customer_id"}
            or not isinstance(lookback, int) or lookback < 1
            or not isinstance(source_field, str)
            or not isinstance(source_values, (tuple, list, set))
        ):
            raise ValueError(f"Rule {rule.rule_code} has invalid load-source parameters.")
        missing_fields: set[str] = set()
        c2c_values = {str(value).strip().upper() for value in source_values}
        groups = self._group_by_entity_and_month(
            transactions,
            grouping_field,
            lambda transaction: transaction.transaction_type == "LOAD",
            missing_fields,
        )
        if any(
            transaction.transaction_type == "LOAD"
            and getattr(transaction, source_field, None) in (None, "")
            for transaction in transactions
        ):
            missing_fields.add(source_field)

        triggers: list[RuleTriggerResult] = []
        for entity, by_month in groups.items():
            latest_month = max(by_month)
            months = self._prior_months(latest_month, lookback - 1) + [latest_month]
            window_loads = [
                item for month in months for item in by_month.get(month, [])
            ]
            if not window_loads or any(
                getattr(item, source_field, None) in (None, "") for item in window_loads
            ):
                missing_fields.add(source_field)
                continue
            if all(
                str(getattr(item, source_field)).strip().upper() in c2c_values
                for item in window_loads
            ):
                triggers.append(self._build_result(max(window_loads, key=self._transaction_sort_key), rule))
        missing = [
            self._data_insufficient(rule, (str(grouping_field), source_field, "txn_date"), missing_fields)
        ] if missing_fields else []
        return triggers, missing

    def _evaluate_currency_conversion_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[DataInsufficientResult]]:
        settlement_field = rule.parameters.get(SETTLEMENT_CURRENCY_PARAMETER)
        originating_field = rule.parameters.get(ORIGINATING_COUNTRY_CURRENCY_PARAMETER)
        if not isinstance(settlement_field, str) or not isinstance(originating_field, str):
            raise ValueError(f"Rule {rule.rule_code} has invalid currency-conversion parameters.")
        missing_fields = self._missing_fields(transactions, (settlement_field, originating_field))
        triggers = [
            self._build_result(transaction, rule)
            for transaction in transactions
            if getattr(transaction, settlement_field, None) not in (None, "")
            and getattr(transaction, originating_field, None) not in (None, "")
            and str(getattr(transaction, settlement_field)).strip().upper()
            != str(getattr(transaction, originating_field)).strip().upper()
        ]
        missing = [
            self._data_insufficient(rule, (settlement_field, originating_field), missing_fields)
        ] if missing_fields else []
        return triggers, missing

    def _evaluate_international_transaction_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[DataInsufficientResult]]:
        transaction_type = rule.parameters.get(TRANSACTION_TYPE_PARAMETER)
        threshold = rule.parameters.get(AMOUNT_THRESHOLD_PARAMETER)
        if not isinstance(transaction_type, str):
            raise ValueError(f"Rule {rule.rule_code} has invalid international parameters.")
        candidates = [
            transaction for transaction in transactions
            if transaction.transaction_type == transaction_type
        ]
        results: list[RuleTriggerResult] = []
        missing_fields: set[str] = set()
        if rule.rule_code in {"R008", "R009"}:
            home_field = rule.parameters.get(HOME_CURRENCY_FIELD_PARAMETER)
            required_fields = ("currency", str(home_field))
            for transaction in candidates:
                transaction_missing = {
                    field for field in required_fields if getattr(transaction, field, None) in (None, "")
                }
                missing_fields.update(transaction_missing)
                if (
                    transaction.amount is not None
                    and transaction.amount > float(threshold)
                    and not transaction_missing
                    and transaction.currency != getattr(transaction, str(home_field))
                ):
                    results.append(self._build_result(transaction, rule))
        else:
            country_field = rule.parameters.get(COUNTRY_FIELD_PARAMETER)
            countries = rule.parameters.get(HIGH_RISK_COUNTRIES_PARAMETER)
            if not isinstance(country_field, str) or not isinstance(countries, (tuple, list, set)):
                raise ValueError(f"Rule {rule.rule_code} has invalid country parameters.")
            required_fields = (country_field,)
            normalized_countries = {str(country).strip().upper() for country in countries}
            for transaction in candidates:
                country = getattr(transaction, country_field, None)
                if country in (None, ""):
                    missing_fields.add(country_field)
                elif str(country).strip().upper() in normalized_countries:
                    results.append(self._build_result(transaction, rule))
        missing = [
            self._data_insufficient(rule, required_fields, missing_fields)
        ] if candidates and missing_fields else []
        return results, missing

    def _evaluate_different_country_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[DataInsufficientResult]]:
        grouping_field = rule.parameters.get(GROUPING_FIELD_PARAMETER)
        country_field = rule.parameters.get(COUNTRY_FIELD_PARAMETER)
        window_hours = rule.parameters.get(TIME_WINDOW_HOURS_PARAMETER)
        if (
            grouping_field not in {"card_number", "proxy_card_number"}
            or not isinstance(country_field, str)
            or not isinstance(window_hours, (int, float))
            or window_hours <= 0
        ):
            raise ValueError(f"Rule {rule.rule_code} has invalid country-window parameters.")
        groups: dict[str, list[Transaction]] = {}
        missing_fields: set[str] = set()
        for transaction in transactions:
            card = getattr(transaction, grouping_field)
            if transaction.txn_date is None:
                missing_fields.add("txn_date")
            if not card:
                missing_fields.add(str(grouping_field))
            if card and transaction.txn_date:
                groups.setdefault(card, []).append(transaction)
                if getattr(transaction, country_field, None) in (None, ""):
                    missing_fields.add(country_field)
        results = []
        window = timedelta(hours=window_hours)
        for card_transactions in groups.values():
            card_transactions.sort(key=self._transaction_sort_key)
            for index, transaction in enumerate(card_transactions):
                country = getattr(transaction, country_field, None)
                if country in (None, ""):
                    continue
                for previous in reversed(card_transactions[:index]):
                    if transaction.txn_date - previous.txn_date > window:
                        break
                    previous_country = getattr(previous, country_field, None)
                    if previous_country not in (None, "") and str(previous_country).strip().upper() != str(country).strip().upper():
                        results.append(self._build_result(transaction, rule))
                        break
        missing = [
            self._data_insufficient(
                rule,
                (str(grouping_field), country_field, "txn_date"),
                missing_fields,
            )
        ] if missing_fields else []
        return results, missing

    @staticmethod
    def _data_insufficient(
        rule: RuleDefinition, required_fields: tuple[str, ...], missing_fields: set[str]
    ) -> DataInsufficientResult:
        return DataInsufficientResult(
            rule_code=rule.rule_code,
            required_fields=required_fields,
            missing_fields=tuple(sorted(missing_fields)),
            reason="Required explicit data is unavailable; no alert was generated from incomplete data.",
        )

    @staticmethod
    def _missing_fields(
        transactions: Iterable[Transaction], fields: tuple[str, ...]
    ) -> set[str]:
        transaction_list = list(transactions)
        return {
            field for field in fields
            if any(getattr(transaction, field, None) in (None, "") for transaction in transaction_list)
        }

    @staticmethod
    def _group_by_entity_and_month(
        transactions: Iterable[Transaction],
        entity_field: str,
        predicate: Callable[[Transaction], bool],
        missing_fields: set[str],
    ) -> dict[str, dict[datetime, list[Transaction]]]:
        groups: dict[str, dict[datetime, list[Transaction]]] = {}
        for transaction in transactions:
            if not predicate(transaction):
                continue
            entity = getattr(transaction, entity_field)
            if not entity:
                missing_fields.add(str(entity_field))
            if transaction.txn_date is None:
                missing_fields.add("txn_date")
            if entity and transaction.txn_date:
                month = RuleEngine._month_start(transaction.txn_date)
                groups.setdefault(entity, {}).setdefault(month, []).append(transaction)
        return groups

    @staticmethod
    def _matches_amount_threshold(transaction: Transaction, rule: RuleDefinition) -> bool:
        transaction_type = rule.parameters.get(TRANSACTION_TYPE_PARAMETER)
        threshold = rule.parameters.get(AMOUNT_THRESHOLD_PARAMETER)
        if transaction.transaction_type != transaction_type or transaction.amount is None:
            return False
        return isinstance(threshold, (int, float)) and transaction.amount > float(threshold)

    def _evaluate_merchant_window(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> list[RuleTriggerResult]:
        merchant_field = rule.parameters.get(MERCHANT_FIELD_PARAMETER)
        threshold = rule.parameters.get(COUNT_THRESHOLD_PARAMETER)
        window_minutes = rule.parameters.get(TIME_WINDOW_MINUTES_PARAMETER)
        if (
            merchant_field not in {"other_party_id", "other_party_name"}
            or not isinstance(threshold, int)
            or threshold < 1
            or not isinstance(window_minutes, (int, float))
            or window_minutes <= 0
        ):
            raise ValueError(f"Rule {rule.rule_code} has invalid window parameters.")

        qualifies = self._qualifier_for(rule)
        groups: dict[str, list[Transaction]] = {}
        for transaction in transactions:
            merchant = getattr(transaction, merchant_field)
            if merchant and transaction.txn_date is not None and qualifies(transaction, rule):
                groups.setdefault(merchant, []).append(transaction)

        results = []
        window = timedelta(minutes=window_minutes)
        for merchant_transactions in groups.values():
            merchant_transactions.sort(key=self._transaction_sort_key)
            trailing_transactions: deque[Transaction] = deque()
            for transaction in merchant_transactions:
                while trailing_transactions and transaction.txn_date - trailing_transactions[0].txn_date > window:
                    trailing_transactions.popleft()
                trailing_transactions.append(transaction)
                if len(trailing_transactions) > threshold:
                    results.append(self._build_result(transaction, rule))
        return results

    @staticmethod
    def _qualifier_for(rule: RuleDefinition) -> Callable[[Transaction, RuleDefinition], bool]:
        if rule.rule_code == "R002":
            return RuleEngine._is_r002_qualifying_transaction
        return RuleEngine._has_qualifying_status

    @staticmethod
    def _has_qualifying_status(transaction: Transaction, rule: RuleDefinition) -> bool:
        return transaction.status in rule.parameters.get(QUALIFYING_STATUSES_PARAMETER, ())

    @staticmethod
    def _is_r002_qualifying_transaction(transaction: Transaction, rule: RuleDefinition) -> bool:
        if RuleEngine._has_qualifying_status(transaction, rule):
            return True
        suffixes = rule.parameters.get(QUALIFYING_TRANSACTION_TYPE_SUFFIXES_PARAMETER, ())
        return bool(transaction.transaction_type) and any(
            transaction.transaction_type.endswith(suffix) for suffix in suffixes
        )

    def _evaluate_historical_rule(
        self, transactions: list[Transaction], rule: RuleDefinition
    ) -> tuple[list[RuleTriggerResult], list[InsufficientHistoryResult]]:
        entity_field = rule.parameters.get(GROUPING_FIELD_PARAMETER)
        lookback = rule.parameters.get(LOOKBACK_MONTHS_PARAMETER)
        increase = rule.parameters.get(INCREASE_PERCENTAGE_PARAMETER)
        if entity_field not in {"card_number", "customer_id"} or not isinstance(lookback, int) or lookback < 1 or not isinstance(increase, (int, float)) or increase < 0:
            raise ValueError(f"Rule {rule.rule_code} has invalid historical parameters.")

        groups: dict[str, list[Transaction]] = {}
        for transaction in transactions:
            entity = getattr(transaction, entity_field)
            if transaction.transaction_type == "LOAD" and entity and transaction.txn_date:
                groups.setdefault(entity, []).append(transaction)

        triggers: list[RuleTriggerResult] = []
        insufficient: list[InsufficientHistoryResult] = []
        for entity, loads in groups.items():
            by_month: dict[datetime, list[Transaction]] = {}
            for load in loads:
                by_month.setdefault(self._month_start(load.txn_date), []).append(load)
            months = sorted(by_month)
            current_months = months[lookback:] if len(months) > lookback else months[-1:]
            for current_month in current_months:
                current_loads = by_month[current_month]
                historical_months = self._prior_months(current_month, lookback)
                available_months = [month for month in historical_months if by_month.get(month)]
                if len(available_months) != lookback:
                    insufficient.append(InsufficientHistoryResult(
                        rule.rule_code, entity_field, entity, current_month, lookback,
                        len(available_months), "missing one or more required historical months",
                    ))
                    continue
                historical_loads = [load for month in historical_months for load in by_month[month]]
                if rule.rule_code == "R005":
                    baseline = self._average_amount(historical_loads)
                    for current_load in current_loads:
                        if current_load.amount is not None and current_load.amount > baseline * (1 + increase / 100):
                            triggers.append(self._build_result(current_load, rule))
                elif rule.rule_code == "R006":
                    historical_totals = [self._total_amount(by_month[month]) for month in historical_months]
                    current_total = self._total_amount(current_loads)
                    baseline = sum(historical_totals) / lookback
                    if current_total > baseline * (1 + increase / 100):
                        triggers.append(self._build_result(max(current_loads, key=self._transaction_sort_key), rule))
                else:
                    baseline = sum(len(by_month[month]) for month in historical_months) / lookback
                    if len(current_loads) > baseline * (1 + increase / 100):
                        triggers.append(self._build_result(max(current_loads, key=self._transaction_sort_key), rule))
        return triggers, insufficient

    @staticmethod
    def _month_start(timestamp: datetime) -> datetime:
        return timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    @staticmethod
    def _prior_months(month: datetime, count: int) -> list[datetime]:
        months = []
        year, month_number = month.year, month.month
        for _ in range(count):
            month_number -= 1
            if month_number == 0:
                year -= 1
                month_number = 12
            months.append(month.replace(year=year, month=month_number))
        return list(reversed(months))

    @staticmethod
    def _average_amount(transactions: list[Transaction]) -> float:
        amounts = [transaction.amount for transaction in transactions]
        if not amounts or any(amount is None for amount in amounts):
            raise ValueError("Historical LOAD amount is missing.")
        return sum(amounts) / len(amounts)

    @staticmethod
    def _total_amount(transactions: list[Transaction]) -> float:
        amounts = [transaction.amount for transaction in transactions]
        if any(amount is None for amount in amounts):
            raise ValueError("LOAD amount is missing.")
        return sum(amounts)

    @staticmethod
    def _transaction_sort_key(transaction: Transaction) -> tuple:
        return (transaction.txn_date, transaction.id or 0, transaction.ext_txn_id or "")

    @staticmethod
    def _build_result(transaction: Transaction, rule: RuleDefinition) -> RuleTriggerResult:
        return RuleTriggerResult(
            rule_code=rule.rule_code, rule_name=rule.name, category=rule.category,
            risk_level=rule.risk_level, priority=rule.priority, transaction_id=transaction.id,
            ext_txn_id=transaction.ext_txn_id, transaction_type=transaction.transaction_type,
            amount=transaction.amount, parameters=rule.parameters,
        )
