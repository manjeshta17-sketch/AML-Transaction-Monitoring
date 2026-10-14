import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.rules import get_rule, list_rules, update_rule
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.rule_configuration import RuleConfiguration
from backend.app.models.transaction import Transaction
from backend.app.schemas.rule_configuration import RuleConfigurationPatch
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.rule_configuration_service import RuleConfigurationService
from backend.app.services.rule_engine import DEFAULT_RULES, RuleEngine


class RuleConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()
        Base.metadata.drop_all(self.engine)
        self.engine.dispose()

    def test_initializes_all_defaults(self):
        RuleConfigurationService.initialize(self.session)
        self.assertEqual(self.session.query(RuleConfiguration).count(), 16)
        self.assertEqual(
            self.session.query(RuleConfiguration).filter_by(rule_code="R004").one().enabled,
            False,
        )

    def test_get_all_and_individual_rules(self):
        rules = list_rules(db=self.session)
        self.assertEqual(len(rules), 16)
        rule = get_rule("R001", db=self.session)
        self.assertEqual(rule.parameters["amount_threshold"], 5000.0)

    def test_updates_enabled_state_and_threshold(self):
        updated = update_rule(
            "R001",
            RuleConfigurationPatch(
                enabled=False,
                parameters={"amount_threshold": 7000.0},
            ),
            db=self.session,
        )
        self.assertFalse(updated.enabled)
        self.assertEqual(updated.parameters["transaction_type"], "LOAD")
        self.assertEqual(updated.parameters["amount_threshold"], 7000.0)

    def test_updates_time_window(self):
        updated = update_rule(
            "R002",
            RuleConfigurationPatch(parameters={"time_window_minutes": 120}),
            db=self.session,
        )
        self.assertEqual(updated.parameters["time_window_minutes"], 120)

    def test_rejects_invalid_parameter_and_unknown_rule(self):
        with self.assertRaises(ValueError):
            RuleConfigurationService.update(
                self.session, "R001",
                {"parameters": {"amount_threshold": -1}},
            )
        with self.assertRaises(KeyError):
            RuleConfigurationService.update(self.session, "R999", {})

    def test_rejects_malformed_country_list_and_invalid_window(self):
        with self.assertRaises(ValueError):
            RuleConfigurationService.update(
                self.session, "R010",
                {"parameters": {"high_risk_countries": ["GB", 44]}},
            )
        with self.assertRaises(ValueError):
            RuleConfigurationService.update(
                self.session, "R002",
                {"parameters": {"time_window_minutes": 0}},
            )

    def test_duplicate_rule_code_is_rejected(self):
        RuleConfigurationService.initialize(self.session)
        self.session.add(
            RuleConfiguration(
                rule_code="R001",
                name="duplicate",
                description="duplicate",
                category="transaction_monitoring",
                risk_level="high",
                priority=1,
                parameters={},
            )
        )
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_engine_uses_persisted_configuration(self):
        RuleConfigurationService.initialize(self.session)
        RuleConfigurationService.update(
            self.session, "R001", {"parameters": {"amount_threshold": 7000.0}}
        )
        transaction = Transaction(transaction_type="LOAD", amount=6000.0)
        self.session.add(transaction)
        self.session.commit()
        result = MonitoringService().run(self.session)
        self.assertEqual(result.alerts_generated, 0)

    def test_disabled_persisted_rule_does_not_generate_alert(self):
        RuleConfigurationService.initialize(self.session)
        RuleConfigurationService.update(self.session, "R001", {"enabled": False})
        self.session.add(Transaction(transaction_type="LOAD", amount=6000.0))
        self.session.commit()
        MonitoringService().run(self.session)
        self.assertEqual(self.session.query(Alert).count(), 0)

    def test_direct_engine_defaults_remain_unchanged(self):
        transaction = Transaction(transaction_type="LOAD", amount=6000.0)
        self.assertEqual(len(RuleEngine().evaluate(transaction)), 1)
