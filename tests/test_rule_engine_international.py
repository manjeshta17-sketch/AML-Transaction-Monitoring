from dataclasses import replace
from datetime import datetime
import unittest

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


def transaction(
    transaction_id: int,
    transaction_type: str,
    *,
    amount: float = 1000.0,
    timestamp: datetime = datetime(2025, 5, 18, 12, 0),
    card_number: str | None = "card-1",
    currency: str | None = "USD",
    home_currency: str | None = "AUD",
    country_code: str | None = "US",
) -> Transaction:
    return Transaction(
        id=transaction_id,
        ext_txn_id=f"transaction-{transaction_id}",
        transaction_type=transaction_type,
        amount=amount,
        txn_date=timestamp,
        card_number=card_number,
        currency=currency,
        home_currency=home_currency,
        country_code=country_code,
    )


def rule(code: str):
    return next(rule for rule in DEFAULT_RULES if rule.rule_code == code)


class InternationalRuleEngineTests(unittest.TestCase):
    def evaluate(self, code, transactions, **parameters):
        configured_rule = rule(code)
        if parameters:
            configured_rule = replace(
                configured_rule,
                parameters={**configured_rule.parameters, **parameters},
            )
        return RuleEngine([configured_rule]).evaluate_with_context(transactions)

    def test_r008_valid_international_pos_and_amount_boundary(self):
        outcome = self.evaluate("R008", [transaction(1, "POS", amount=1000.0)])
        boundary = self.evaluate("R008", [transaction(2, "POS", amount=999.0)])

        self.assertEqual([result.transaction_id for result in outcome.triggers], [1])
        self.assertEqual(boundary.triggers, [])

    def test_r009_valid_international_atm_and_configurable_threshold(self):
        outcome = self.evaluate(
            "R009",
            [transaction(1, "ATM", amount=501.0)],
            amount_threshold=500.0,
        )

        self.assertEqual([result.transaction_id for result in outcome.triggers], [1])

    def test_r008_and_r009_do_not_trigger_in_home_currency(self):
        transactions = [
            transaction(1, "POS", currency="AUD"),
            transaction(2, "ATM", currency="AUD"),
        ]

        self.assertEqual(self.evaluate("R008", [transactions[0]]).triggers, [])
        self.assertEqual(self.evaluate("R009", [transactions[1]]).triggers, [])

    def test_r010_and_r011_match_configurable_high_risk_countries(self):
        pos = self.evaluate("R010", [transaction(1, "POS", amount=1.0, country_code="IR")], high_risk_countries=("IR",))
        atm = self.evaluate("R011", [transaction(2, "ATM", amount=1.0, country_code="KP")], high_risk_countries=("KP",))

        self.assertEqual([result.transaction_id for result in pos.triggers], [1])
        self.assertEqual([result.transaction_id for result in atm.triggers], [2])

    def test_r010_does_not_match_non_high_risk_country(self):
        outcome = self.evaluate("R010", [transaction(1, "POS", country_code="AU")], high_risk_countries=("IR",))

        self.assertEqual(outcome.triggers, [])

    def test_r012_triggers_for_different_countries_within_inclusive_window(self):
        transactions = [
            transaction(1, "POS", timestamp=datetime(2025, 5, 18, 0, 0), country_code="AU"),
            transaction(2, "POS", timestamp=datetime(2025, 5, 18, 12, 0), country_code="US"),
        ]

        outcome = self.evaluate("R012", transactions)

        self.assertEqual([result.transaction_id for result in outcome.triggers], [2])

    def test_r012_does_not_trigger_for_same_country_outside_window_or_different_card(self):
        same_country = [
            transaction(1, "POS", country_code="AU"),
            transaction(2, "POS", timestamp=datetime(2025, 5, 18, 1, 0), country_code="AU"),
        ]
        outside_window = [
            transaction(3, "POS", timestamp=datetime(2025, 5, 18, 0, 0), country_code="AU"),
            transaction(4, "POS", timestamp=datetime(2025, 5, 19, 0, 1), country_code="US"),
        ]
        different_card = [
            transaction(5, "POS", card_number="card-1", country_code="AU"),
            transaction(6, "POS", card_number="card-2", timestamp=datetime(2025, 5, 18, 1, 0), country_code="US"),
        ]

        self.assertEqual(self.evaluate("R012", same_country).triggers, [])
        self.assertEqual(self.evaluate("R012", outside_window).triggers, [])
        self.assertEqual(self.evaluate("R012", different_card).triggers, [])

    def test_r012_supports_configurable_window(self):
        transactions = [
            transaction(1, "POS", timestamp=datetime(2025, 5, 18, 0, 0), country_code="AU"),
            transaction(2, "POS", timestamp=datetime(2025, 5, 18, 2, 0), country_code="US"),
        ]

        outcome = self.evaluate("R012", transactions, time_window_hours=1)

        self.assertEqual(outcome.triggers, [])

    def test_missing_required_data_returns_data_insufficient_results(self):
        transactions = [
            transaction(1, "POS", home_currency=None, country_code=None),
            transaction(2, "ATM", home_currency=None, country_code=None),
        ]

        outcome = RuleEngine().evaluate_with_context(transactions)

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(
            {result.rule_code for result in outcome.data_insufficient},
            {"R008", "R009", "R010", "R011", "R012", "R013", "R016"},
        )
        self.assertTrue(all(not result.missing_fields == () for result in outcome.data_insufficient))

    def test_disabled_rules_do_not_execute(self):
        disabled_rules = [replace(rule(code), enabled=False) for code in ("R008", "R009", "R010", "R011", "R012")]

        outcome = RuleEngine(disabled_rules).evaluate_with_context(
            [transaction(1, "POS"), transaction(2, "ATM")]
        )

        self.assertEqual(outcome.triggers, [])
        self.assertEqual(outcome.data_insufficient, [])


if __name__ == "__main__":
    unittest.main()
