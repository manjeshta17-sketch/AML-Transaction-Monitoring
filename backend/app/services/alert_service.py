from sqlalchemy.orm import Session

from backend.app.models.alert import Alert
from backend.app.models.transaction import Transaction
from backend.app.schemas.rule import RuleTriggerResult


class AlertService:
    """Creates persistent alerts from rule triggers without evaluating rules."""

    @staticmethod
    def create_alert(
        transaction: Transaction,
        trigger: RuleTriggerResult,
        db: Session,
    ) -> Alert | None:
        if transaction.id is None:
            raise ValueError("Alerts can only be created for persisted transactions.")

        existing_alert = (
            db.query(Alert)
            .filter(
                Alert.transaction_id == transaction.id,
                Alert.rule_code == trigger.rule_code,
            )
            .one_or_none()
        )
        if existing_alert is not None:
            return None

        alert = Alert(
            alert_code=AlertService.alert_code_for(transaction.id, trigger.rule_code),
            rule_code=trigger.rule_code,
            rule_name=trigger.rule_name,
            description=f"Rule {trigger.rule_code} matched: {trigger.rule_name}",
            transaction_id=transaction.id,
            customer_id=transaction.customer_id,
            card_number=transaction.card_number,
            amount=transaction.amount,
            risk_level=trigger.risk_level,
            priority=trigger.priority,
            status="OPEN",
        )
        db.add(alert)
        return alert

    @staticmethod
    def alert_code_for(transaction_id: int, rule_code: str) -> str:
        """Return a deterministic, human-readable code for one alert identity."""
        return f"ALT-{rule_code}-T{transaction_id:08d}"
