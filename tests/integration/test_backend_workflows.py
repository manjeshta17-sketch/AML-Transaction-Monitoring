from datetime import datetime

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.api.alerts import (
    create_case_from_alert,
    get_alert,
    list_alerts_endpoint,
    update_alert_status,
)
from backend.app.api.cases import (
    add_case_comment,
    get_case,
    list_cases,
    update_case_assignment,
    update_case_status,
)
from backend.app.api.dashboard import dashboard_summary
from backend.app.api.rules import get_rule, update_rule
from backend.app.api.transactions import get_transaction, list_transactions
from backend.app.core.database import Base
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.transaction import Transaction
from backend.app.schemas.alert import AlertStatusUpdate
from backend.app.schemas.case import CaseAssignmentUpdate, CaseCommentCreate, CaseStatusUpdate
from backend.app.schemas.rule_configuration import RuleConfigurationPatch
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.rule_configuration_service import RuleConfigurationService


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        RuleConfigurationService.initialize(session)
        session.add_all(
            [
                Transaction(
                    txn_date=datetime(2025, 5, 18, 10, 0),
                    ext_txn_id="integration-load-1",
                    transaction_type="LOAD",
                    amount=6000,
                    customer_id="integration-customer",
                    card_number="integration-card",
                    currency="036",
                ),
                Transaction(
                    txn_date=datetime(2025, 5, 18, 10, 1),
                    ext_txn_id="integration-transfer-1",
                    transaction_type="CARD_TO_CARD",
                    amount=1200,
                    customer_id="integration-customer",
                    card_number="integration-card",
                    currency="036",
                ),
            ]
        )
        session.commit()
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def _run_monitoring(db: Session):
    result = MonitoringService().run(db)
    db.expire_all()
    return result


def test_imported_transactions_monitor_once_and_remain_idempotent(db: Session):
    first = _run_monitoring(db)
    second = _run_monitoring(db)

    assert first.transactions_evaluated == 2
    assert first.alerts_generated == 2
    assert first.alerts_by_rule == {"R001": 1, "R015": 1}
    assert second.alerts_generated == 0
    assert db.query(Alert).count() == 2

    alert_snapshot = [
        (alert.alert_code, alert.rule_code, alert.status)
        for alert in db.query(Alert).order_by(Alert.id)
    ]
    _run_monitoring(db)
    assert [
        (alert.alert_code, alert.rule_code, alert.status)
        for alert in db.query(Alert).order_by(Alert.id)
    ] == alert_snapshot


def test_persisted_rule_configuration_changes_monitoring_only_for_that_rule(db: Session):
    original_r001 = get_rule("R001", db=db)
    assert original_r001.enabled is True

    update_rule(
        "R001",
        RuleConfigurationPatch(parameters={"transaction_type": "LOAD", "amount_threshold": 7000}),
        db=db,
    )
    result = _run_monitoring(db)

    assert result.alerts_by_rule == {"R015": 1}
    assert db.query(Alert).filter(Alert.rule_code == "R001").count() == 0
    assert db.query(Alert).filter(Alert.rule_code == "R015").count() == 1


def test_alert_case_transaction_relationship_workflow(db: Session):
    _run_monitoring(db)
    transaction = db.query(Transaction).filter_by(ext_txn_id="integration-load-1").one()
    alert = db.query(Alert).filter_by(transaction_id=transaction.id, rule_code="R001").one()

    transaction_detail = get_transaction(transaction.id, db=db)
    alert_detail = get_alert(alert.id, db=db)
    assert transaction_detail.alert_count == 1
    assert transaction_detail.alerts[0].id == alert.id
    assert alert_detail.transaction.id == transaction.id

    case = create_case_from_alert(alert.id, db=db)
    db.expire_all()
    case_detail = get_case(case.id, db=db)
    assert case_detail.alert_id == alert.id
    assert case_detail.alert.transaction_id == transaction.id
    assert case_detail.transaction.id == transaction.id

    update_case_assignment(case.id, CaseAssignmentUpdate(assigned_to="analyst-1"), db=db)
    update_case_status(case.id, CaseStatusUpdate(status="IN_PROGRESS"), db=db)
    comment = add_case_comment(
        case.id,
        CaseCommentCreate(comment="Reviewed transaction context.", created_by="analyst-1"),
        db=db,
    )
    update_case_status(case.id, CaseStatusUpdate(status="CLOSED"), db=db)
    closed_detail = get_case(case.id, db=db)

    assert closed_detail.status == "CLOSED"
    assert closed_detail.closed_at is not None
    assert closed_detail.assigned_to == "analyst-1"
    assert closed_detail.comments[0].id == comment.id


def test_duplicate_case_returns_conflict_and_preserves_original(db: Session):
    _run_monitoring(db)
    alert = db.query(Alert).filter_by(rule_code="R001").one()
    original = create_case_from_alert(alert.id, db=db)

    with pytest.raises(HTTPException) as error:
        create_case_from_alert(alert.id, db=db)

    assert error.value.status_code == 409
    assert db.query(Case).count() == 1
    assert db.query(Case).one().id == original.id


def test_dashboard_changes_when_alert_and_case_workflows_change_state(db: Session):
    _run_monitoring(db)
    before = dashboard_summary(db=db)
    assert before.alerts.total_alerts == 2
    assert before.cases.total_cases == 0
    assert before.alerts.open_alerts == 2

    alert = db.query(Alert).filter_by(rule_code="R001").one()
    case = create_case_from_alert(alert.id, db=db)
    update_alert_status(alert.id, AlertStatusUpdate(status="CLOSED"), db=db)
    update_case_status(case.id, CaseStatusUpdate(status="CLOSED"), db=db)

    after = dashboard_summary(db=db)
    assert after.alerts.total_alerts == 2
    assert after.alerts.closed_alerts == 1
    assert after.alerts.open_alerts == 1
    assert after.cases.total_cases == 1
    assert after.cases.by_status["CLOSED"] == 1


def test_search_filters_find_consistent_transaction_alert_and_case_records(db: Session):
    _run_monitoring(db)
    transaction = db.query(Transaction).filter_by(ext_txn_id="integration-load-1").one()
    alert = db.query(Alert).filter_by(transaction_id=transaction.id).one()
    create_case_from_alert(alert.id, db=db)

    transaction_results = list_transactions(search="integration-load-1", db=db)
    alert_results = list_alerts_endpoint(search=alert.alert_code, db=db)
    case_results = list_cases(search=alert.alert_code, db=db)

    assert transaction_results.total == 1
    assert transaction_results.transactions[0].id == transaction.id
    assert alert_results.total == 1
    assert alert_results.alerts[0].transaction_id == transaction.id
    assert case_results.total == 1
    assert case_results.cases[0].alert_id == alert.id


def test_invalid_integration_workflows_are_controlled(db: Session):
    with pytest.raises(HTTPException) as unknown_transaction:
        get_transaction(999999, db=db)
    assert unknown_transaction.value.status_code == 404

    with pytest.raises(HTTPException) as unknown_alert:
        get_alert(999999, db=db)
    assert unknown_alert.value.status_code == 404

    with pytest.raises(HTTPException) as unknown_case:
        get_case(999999, db=db)
    assert unknown_case.value.status_code == 404

    with pytest.raises(HTTPException) as unknown_rule:
        get_rule("R999", db=db)
    assert unknown_rule.value.status_code == 404

    with pytest.raises(HTTPException) as invalid_page:
        list_transactions(page=0, db=db)
    assert invalid_page.value.status_code == 422

    with pytest.raises(HTTPException) as invalid_status:
        update_alert_status(999999, AlertStatusUpdate(status="NOT_A_STATUS"), db=db)
    assert invalid_status.value.status_code == 422

    with pytest.raises(HTTPException) as invalid_rule:
        update_rule("R001", RuleConfigurationPatch(parameters={"unsafe": "value"}), db=db)
    assert invalid_rule.value.status_code == 422
