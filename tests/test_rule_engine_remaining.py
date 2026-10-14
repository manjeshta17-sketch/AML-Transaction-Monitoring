from dataclasses import replace
from datetime import datetime
import unittest

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


def tx(
    transaction_id: int,
    transaction_type: str,
    timestamp: datetime,
    *,
    card: str = "card-1",
    domestic_status: str | None = "DOMESTIC",
    load_source: str | None = "C2C",
    settlement_currency: str | None = "USD",
    originating_currency: str | None = "AUD",
) -> Transaction:
    return Transaction(
        id=transaction_id,
        ext_txn_id=f"tx-{transaction_id}",
        transaction_type=transaction_type,
        txn_date=timestamp,
        card_number=card,
        amount=10.0,
        domestic_status=domestic_status,
        load_source=load_source,
        settlement_currency=settlement_currency,
        originating_country_currency=originating_currency,
    )


def rule(code: str):
    return next(item for item in DEFAULT_RULES if item.rule_code == code)


class RemainingRuleEngineTests(unittest.TestCase):
    def evaluate(self, code, transactions, **parameters):
        configured = rule(code)
        if parameters:
            configured = replace(configured, parameters={**configured.parameters, **parameters})
        return RuleEngine([configured]).evaluate_with_context(transactions)

    def test_r013_triggers_above_historical_domestic_atm_frequency(self):
        historical = [
            tx(index, "ATM", datetime(2025, month, 15))
            for month in range(1, 7) for index in (month,)
        ]
        current = [
            tx(10 + index, "ATM", datetime(2025, 7, index + 1))
            for index in range(2)
        ]

        outcome = self.evaluate("R013", historical + current)

        self.assertEqual([item.transaction_id for item in outcome.triggers], [11])

    def test_r013_exact_boundary_non_atm_and_configurable_parameters(self):
        historical = [
            tx(index, "ATM", datetime(2025, month, 15))
            for month in range(1, 5) for index in (month,)
        ]
        current = [tx(10, "ATM", datetime(2025, 5, 1))]
        non_atm = tx(11, "POS", datetime(2025, 5, 2))

        boundary = self.evaluate(
            "R013", historical + current + [non_atm],
            lookback_months=4, increase_percentage=0.0,
        )
        self.assertEqual(boundary.triggers, [])

    def test_r013_requires_explicit_domestic_status(self):
        transactions = [tx(1, "ATM", datetime(2025, 5, 1), domestic_status=None)]

        outcome = self.evaluate("R013", transactions)

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(outcome.data_insufficient[0].missing_fields, ("domestic_status",))

    def test_r014_triggers_only_when_all_load_sources_are_c2c(self):
        transactions = [
            tx(1, "LOAD", datetime(2025, 3, 1), load_source="C2C"),
            tx(2, "LOAD", datetime(2025, 4, 1), load_source="C2C"),
            tx(3, "LOAD", datetime(2025, 5, 31), load_source="C2C"),
        ]

        outcome = self.evaluate("R014", transactions)

        self.assertEqual([item.transaction_id for item in outcome.triggers], [3])

    def test_r014_does_not_trigger_for_non_c2c_or_missing_source(self):
        non_c2c = [
            tx(1, "LOAD", datetime(2025, 3, 1), load_source="C2C"),
            tx(2, "LOAD", datetime(2025, 5, 1), load_source="CARD"),
        ]
        missing = [tx(3, "LOAD", datetime(2025, 5, 1), load_source=None)]

        self.assertEqual(self.evaluate("R014", non_c2c).triggers, [])
        self.assertEqual(self.evaluate("R014", missing).triggers, [])
        self.assertTrue(self.evaluate("R014", missing).data_insufficient)

    def test_r014_ignores_non_load_and_supports_customer_grouping(self):
        transactions = [
            tx(1, "POS", datetime(2025, 3, 1), card="card-2"),
            tx(2, "LOAD", datetime(2025, 5, 1), card="card-2"),
        ]

        outcome = self.evaluate(
            "R014", transactions, grouping_field="customer_id",
        )

        self.assertEqual(outcome.triggers, [])

    def test_r016_triggers_only_when_currencies_differ(self):
        different = [tx(1, "POS", datetime(2025, 5, 1))]
        same = [tx(2, "POS", datetime(2025, 5, 1), originating_currency="USD")]

        self.assertEqual([item.transaction_id for item in self.evaluate("R016", different).triggers], [1])
        self.assertEqual(self.evaluate("R016", same).triggers, [])

    def test_r016_requires_explicit_currency_fields(self):
        transactions = [tx(1, "POS", datetime(2025, 5, 1), settlement_currency=None)]

        outcome = self.evaluate("R016", transactions)

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(outcome.data_insufficient[0].missing_fields, ("settlement_currency",))

    def test_remaining_rules_can_be_disabled(self):
        disabled = [replace(rule(code), enabled=False) for code in ("R013", "R014", "R016")]

        outcome = RuleEngine(disabled).evaluate_with_context(
            [tx(1, "ATM", datetime(2025, 5, 1))]
        )

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(outcome.data_insufficient, [])


if __name__ == "__main__":
    unittest.main()
