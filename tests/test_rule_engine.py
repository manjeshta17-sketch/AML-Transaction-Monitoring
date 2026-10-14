from dataclasses import replace
import unittest

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


def transaction(transaction_type: str, amount: float) -> Transaction:
    return Transaction(
        id=123,
        ext_txn_id="transaction-123",
        transaction_type=transaction_type,
        amount=amount,
    )


class RuleEngineTests(unittest.TestCase):
    def test_r001_triggers_for_a_high_value_load(self):
        results = RuleEngine().evaluate(transaction("LOAD", 5000.01))

        self.assertEqual([result.rule_code for result in results], ["R001"])
        self.assertEqual(results[0].ext_txn_id, "transaction-123")

    def test_r001_uses_its_configured_threshold(self):
        adjusted_rule = replace(
            DEFAULT_RULES[0],
            parameters={"transaction_type": "LOAD", "amount_threshold": 6000.0},
        )
        engine = RuleEngine([adjusted_rule])

        self.assertEqual(engine.evaluate(transaction("LOAD", 5500.0)), [])
        self.assertEqual(len(engine.evaluate(transaction("LOAD", 6000.01))), 1)

    def test_r015_triggers_for_a_high_value_card_to_card_transfer(self):
        results = RuleEngine().evaluate(transaction("CARD_TO_CARD", 1000.01))

        self.assertEqual([result.rule_code for result in results], ["R015"])

    def test_disabled_rules_do_not_execute(self):
        disabled_rule = replace(DEFAULT_RULES[0], enabled=False)

        self.assertEqual(RuleEngine([disabled_rule]).evaluate(transaction("LOAD", 9000)), [])

    def test_no_match_returns_an_empty_result(self):
        self.assertEqual(RuleEngine().evaluate(transaction("POS", 9000)), [])
        self.assertEqual(RuleEngine().evaluate(transaction("LOAD", 5000)), [])


if __name__ == "__main__":
    unittest.main()
