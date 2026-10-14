from collections import Counter
from dataclasses import dataclass, field
import logging

from sqlalchemy.orm import Session

from backend.app.models.transaction import Transaction
from backend.app.services.alert_service import AlertService
from backend.app.services.rule_engine import RuleEngine
from backend.app.services.rule_configuration_service import RuleConfigurationService
from backend.app.services.ml_service import enrich_transactions


logger = logging.getLogger(__name__)
from backend.app.schemas.rule import InsufficientHistoryResult
from backend.app.schemas.rule import DataInsufficientResult


@dataclass(frozen=True)
class MonitoringRunResult:
    transactions_evaluated: int
    alerts_generated: int
    alerts_by_rule: dict[str, int]
    insufficient_history: list[InsufficientHistoryResult]
    data_insufficient: list[DataInsufficientResult] = field(default_factory=list)


class MonitoringService:
    """Coordinates transaction evaluation and alert persistence."""

    def __init__(
        self,
        rule_engine: RuleEngine | None = None,
        alert_service: AlertService | None = None,
    ):
        self._load_persisted_rules = rule_engine is None
        self.rule_engine = rule_engine or RuleEngine()
        self.alert_service = alert_service or AlertService()

    def run(self, db: Session) -> MonitoringRunResult:
        alerts_by_rule: Counter[str] = Counter()

        try:
            if self._load_persisted_rules:
                self.rule_engine = RuleEngine(RuleConfigurationService.load_rules(db))
            transactions = db.query(Transaction).order_by(Transaction.id).all()
            transactions_by_id = {transaction.id: transaction for transaction in transactions}
            outcome = self.rule_engine.evaluate_with_context(transactions)
            for trigger in outcome.triggers:
                transaction = transactions_by_id[trigger.transaction_id]
                alert = self.alert_service.create_alert(transaction, trigger, db)
                if alert is not None:
                    alerts_by_rule[alert.rule_code] += 1

            db.commit()
        except Exception:
            db.rollback()
            raise

        try:
            enrich_transactions(db, transactions)
        except Exception:
            db.rollback()
            logger.exception("ML enrichment failed after deterministic monitoring completed")

        return MonitoringRunResult(
            transactions_evaluated=len(transactions),
            alerts_generated=sum(alerts_by_rule.values()),
            alerts_by_rule=dict(alerts_by_rule),
            insufficient_history=outcome.insufficient_history,
            data_insufficient=outcome.data_insufficient,
        )
