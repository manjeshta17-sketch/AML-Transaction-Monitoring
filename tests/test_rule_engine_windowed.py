from dataclasses import replace
from datetime import datetime, timedelta
import unittest

from backend.app.models.transaction import Transaction
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


def transaction(transaction_id, timestamp, merchant="merchant-1", status="PAYMENT_SUCCESS", transaction_type="POS"):
    return Transaction(
        id=transaction_id, ext_txn_id=f"transaction-{transaction_id}", txn_date=timestamp,
        other_party_id=merchant, status=status, transaction_type=transaction_type, amount=10.0,
    )


class WindowedRuleEngineTests(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2025, 5, 12, 12, 0, 0)
        self.r002 = next(rule for rule in DEFAULT_RULES if rule.rule_code == "R002")
        self.r003 = next(rule for rule in DEFAULT_RULES if rule.rule_code == "R003")
        self.r004 = next(rule for rule in DEFAULT_RULES if rule.rule_code == "R004")

    def evaluate_r003(self, transactions, rule=None):
        return RuleEngine([rule or self.r003]).evaluate_transactions(transactions)

    def test_exactly_three_successes_do_not_trigger_a_greater_than_three_rule(self):
        transactions = [transaction(index, self.start + timedelta(minutes=index * 10)) for index in range(3)]
        self.assertEqual(self.evaluate_r003(transactions), [])

    def test_four_successes_within_one_hour_trigger_on_the_fourth_transaction(self):
        transactions = [transaction(index, self.start + timedelta(minutes=index * 10)) for index in range(4)]
        results = self.evaluate_r003(transactions)
        self.assertEqual([result.transaction_id for result in results], [3])
        self.assertEqual(results[0].rule_code, "R003")

    def test_transactions_outside_the_window_do_not_trigger(self):
        transactions = [
            transaction(index, self.start + timedelta(minutes=offset))
            for index, offset in enumerate((0, 20, 40, 61))
        ]
        self.assertEqual(self.evaluate_r003(transactions), [])

    def test_exactly_one_hour_apart_is_included_in_the_window(self):
        transactions = [
            transaction(index, self.start + timedelta(minutes=offset))
            for index, offset in enumerate((0, 20, 40, 60))
        ]
        self.assertEqual([result.transaction_id for result in self.evaluate_r003(transactions)], [3])

    def test_merchants_are_evaluated_independently(self):
        transactions = [transaction(index, self.start + timedelta(minutes=index), "merchant-a") for index in range(2)]
        transactions += [transaction(index + 2, self.start + timedelta(minutes=index), "merchant-b") for index in range(2)]
        self.assertEqual(self.evaluate_r003(transactions), [])

    def test_count_threshold_is_configurable(self):
        configured_rule = replace(self.r003, parameters={**self.r003.parameters, "count_threshold": 2})
        transactions = [transaction(index, self.start + timedelta(minutes=index)) for index in range(3)]
        self.assertEqual([result.transaction_id for result in self.evaluate_r003(transactions, configured_rule)], [2])

    def test_time_window_is_configurable(self):
        configured_rule = replace(self.r003, parameters={**self.r003.parameters, "time_window_minutes": 30})
        transactions = [
            transaction(index, self.start + timedelta(minutes=offset))
            for index, offset in enumerate((0, 10, 20, 40))
        ]
        self.assertEqual(self.evaluate_r003(transactions, configured_rule), [])

    def test_disabled_window_rule_does_not_execute(self):
        disabled_rule = replace(self.r003, enabled=False)
        transactions = [transaction(index, self.start + timedelta(minutes=index)) for index in range(4)]
        self.assertEqual(self.evaluate_r003(transactions, disabled_rule), [])

    def test_r002_counts_reversals_without_treating_them_as_declines(self):
        transactions = [transaction(index, self.start + timedelta(minutes=index), status="REVERSED") for index in range(4)]
        results = RuleEngine([self.r002]).evaluate_transactions(transactions)
        self.assertEqual([result.transaction_id for result in results], [3])

    def test_r004_is_disabled_due_to_data_limitations(self):
        transactions = [transaction(1, self.start, status="REVERSED", transaction_type="POS")]
        self.assertFalse(self.r004.enabled)
        self.assertEqual(self.r004.parameters["implementation_status"], "DATA_INSUFFICIENT")
        self.assertEqual(RuleEngine([self.r004]).evaluate_transactions(transactions), [])
