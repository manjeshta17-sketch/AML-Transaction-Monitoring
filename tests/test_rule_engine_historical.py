from dataclasses import replace
from datetime import datetime
import unittest

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


def load(
    transaction_id: int,
    timestamp: datetime,
    amount: float = 100.0,
    *,
    card_number: str | None = "card-1",
    customer_id: str | None = "customer-1",
    transaction_type: str = "LOAD",
) -> Transaction:
    return Transaction(
        id=transaction_id,
        ext_txn_id=f"transaction-{transaction_id}",
        txn_date=timestamp,
        amount=amount,
        card_number=card_number,
        customer_id=customer_id,
        transaction_type=transaction_type,
    )


def rule(code: str):
    return next(rule for rule in DEFAULT_RULES if rule.rule_code == code)


class HistoricalRuleEngineTests(unittest.TestCase):
    def evaluate(self, code, transactions, **parameters):
        configured_rule = rule(code)
        if parameters:
            configured_rule = replace(
                configured_rule,
                parameters={**configured_rule.parameters, **parameters},
            )
        return RuleEngine([configured_rule]).evaluate_with_context(transactions)

    def test_r005_triggers_above_the_six_month_single_load_average(self):
        historical = [
            load(index, datetime(2025, month, 15), amount=100.0)
            for index, month in enumerate(range(1, 7))
        ]
        current = load(7, datetime(2025, 7, 1), amount=200.01)

        outcome = self.evaluate("R005", historical + [current])

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [7])
        self.assertEqual(outcome.insufficient_history, [])

    def test_r005_does_not_trigger_at_the_exact_threshold(self):
        historical = [
            load(index, datetime(2025, month, 15), amount=100.0)
            for index, month in enumerate(range(1, 7))
        ]
        current = load(7, datetime(2025, 7, 31, 23, 59, 59), amount=200.0)

        self.assertEqual(self.evaluate("R005", historical + [current]).triggers, [])

    def test_r005_ignores_non_load_transactions(self):
        historical = [
            load(index, datetime(2025, month, 15), amount=100.0)
            for index, month in enumerate(range(1, 7))
        ]
        non_load = load(7, datetime(2025, 7, 1), amount=1000.0, transaction_type="POS")

        self.assertEqual(self.evaluate("R005", historical + [non_load]).triggers, [])

    def test_r005_supports_configurable_threshold_and_lookback(self):
        historical = [
            load(index, datetime(2025, month, 15), amount=100.0)
            for index, month in enumerate(range(1, 5))
        ]
        current = load(5, datetime(2025, 5, 1), amount=151.0)

        outcome = self.evaluate(
            "R005",
            historical + [current],
            lookback_months=4,
            increase_percentage=50.0,
        )

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [5])

    def test_r006_triggers_when_current_month_total_is_more_than_fifty_percent_above_average(self):
        historical = [
            load(index, datetime(2025 if month <= 12 else 2024, month if month <= 12 else 12, 15))
            for index, month in enumerate(range(1, 13))
        ]
        current = load(13, datetime(2026, 1, 1), amount=150.01)

        outcome = self.evaluate("R006", historical + [current])

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [13])

    def test_r006_does_not_trigger_at_the_exact_threshold(self):
        historical = [
            load(index, datetime(2025, month, 15))
            for index, month in enumerate(range(1, 13))
        ]
        current = load(13, datetime(2026, 1, 31, 23, 59, 59), amount=150.0)

        self.assertEqual(self.evaluate("R006", historical + [current]).triggers, [])

    def test_r006_supports_configurable_threshold_and_lookback(self):
        historical = [
            load(index, datetime(2025, month, 15))
            for index, month in enumerate(range(1, 5))
        ]
        current = load(5, datetime(2025, 5, 1), amount=121.0)

        outcome = self.evaluate(
            "R006",
            historical + [current],
            lookback_months=4,
            increase_percentage=20.0,
        )

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [5])

    def test_r007_triggers_when_current_month_count_is_more_than_fifty_percent_above_average(self):
        historical = [
            load((month - 1) * 2 + offset, datetime(2025, month, 15), amount=10.0)
            for month in range(1, 7)
            for offset in range(2)
        ]
        current = [
            load(20 + offset, datetime(2025, 7, 1 + offset), amount=10.0)
            for offset in range(4)
        ]

        outcome = self.evaluate("R007", historical + current)

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [23])

    def test_r007_does_not_trigger_at_the_exact_threshold(self):
        historical = [
            load((month - 1) * 2 + offset, datetime(2025, month, 15), amount=10.0)
            for month in range(1, 7)
            for offset in range(2)
        ]
        current = [
            load(20 + offset, datetime(2025, 7, 1 + offset), amount=10.0)
            for offset in range(3)
        ]

        self.assertEqual(self.evaluate("R007", historical + current).triggers, [])

    def test_r007_supports_customer_grouping_and_configurable_lookback(self):
        historical = [
            load(index, datetime(2025, month, 15), customer_id="customer-2")
            for index, month in enumerate(range(1, 5))
        ]
        current = [
            load(5, datetime(2025, 5, 1), customer_id="customer-2"),
            load(6, datetime(2025, 5, 2), customer_id="customer-2"),
        ]

        outcome = self.evaluate(
            "R007",
            historical + current,
            grouping_field="customer_id",
            lookback_months=4,
            increase_percentage=50.0,
        )

        self.assertEqual([trigger.transaction_id for trigger in outcome.triggers], [6])

    def test_historical_rules_report_insufficient_history_without_triggers(self):
        transactions = [
            load(1, datetime(2025, 1, 31, 23, 59, 59)),
            load(2, datetime(2025, 3, 1)),
        ]

        outcome = self.evaluate("R005", transactions)

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(len(outcome.insufficient_history), 1)
        self.assertEqual(
            {(result.evaluation_month.month, result.available_months) for result in outcome.insufficient_history},
            {(3, 1)},
        )

    def test_disabled_historical_rule_does_not_execute(self):
        disabled_rule = replace(rule("R005"), enabled=False)
        transactions = [load(1, datetime(2025, 1, 15))]

        outcome = RuleEngine([disabled_rule]).evaluate_with_context(transactions)

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(outcome.insufficient_history, [])


if __name__ == "__main__":
    unittest.main()
