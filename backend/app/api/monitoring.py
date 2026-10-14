from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.models.transaction import Transaction
from backend.app.services.monitoring_service import MonitoringService
from backend.app.services.rule_engine import RuleEngine, RULE_CLASSIFICATIONS, DEFAULT_RULES
from backend.app.schemas.errors import ErrorResponse
from backend.app.schemas.monitoring import MonitoringRunResponse, RuleCoverageItem


router = APIRouter(prefix="/monitoring", tags=["Monitoring"])


@router.post(
    "/run",
    response_model=MonitoringRunResponse,
    summary="Run transaction monitoring",
    description="Evaluates enabled rules and persists new alerts. Repeated runs are idempotent.",
    responses={
        409: {"model": ErrorResponse, "description": "A database conflict prevented persistence."},
        500: {"model": ErrorResponse, "description": "Unexpected monitoring failure."},
    },
)
def run_monitoring(db: Session = Depends(get_db)):
    result = MonitoringService().run(db)
    return {
        "transactions_evaluated": result.transactions_evaluated,
        "alerts_generated": result.alerts_generated,
        "alerts_by_rule": result.alerts_by_rule,
        "insufficient_history": result.insufficient_history,
        "data_insufficient": result.data_insufficient,
    }


@router.get(
    "/rule-coverage",
    response_model=list[RuleCoverageItem],
    summary="Get AML rule data coverage",
    description="Returns which R001-R016 rules have sufficient data to run and which are data-insufficient.",
)
def get_rule_coverage(db: Session = Depends(get_db)):
    transactions = db.query(Transaction).all()
    rule_engine = RuleEngine()
    coverage = []

    for rule in DEFAULT_RULES:
        if not rule.enabled:
            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=False,
                reason="Rule is disabled",
                alerts_generated=0,
            ))
            continue

        classification = RULE_CLASSIFICATIONS.get(rule.rule_code)

        # Single transaction rules (R001, R015)
        if classification == "single_transaction":
            has_data = any(
                rule_engine._matches_amount_threshold(tx, rule)
                for tx in transactions
            )
            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=has_data,
                reason="Sufficient data" if has_data else "No matching transactions",
                alerts_generated=sum(1 for tx in transactions if rule_engine._matches_amount_threshold(tx, rule)),
            ))

        # Windowed rules (R002, R003)
        elif classification == "merchant_window":
            merchant_field = rule.parameters.get("merchant_field")
            has_merchant_data = any(
                getattr(tx, merchant_field, None) not in (None, "")
                for tx in transactions
            )
            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=has_merchant_data,
                reason="Sufficient data" if has_merchant_data else f"Missing {merchant_field} data",
                alerts_generated=0,  # Would need full evaluation
            ))

        # Historical rules (R005, R006, R007)
        elif classification == "historical":
            grouping_field = rule.parameters.get("grouping_field")
            lookback = rule.parameters.get("lookback_months")
            has_load_data = any(
                tx.transaction_type == "LOAD" and getattr(tx, grouping_field, None)
                for tx in transactions
            )
            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=has_load_data,
                reason="Sufficient data" if has_load_data else f"Missing LOAD history for {grouping_field}",
                alerts_generated=0,
            ))

        # Data-dependent rules (R008-R014, R016)
        elif classification == "data_dependent":
            required_fields = []
            missing_fields = []

            if rule.rule_code in ["R008", "R009"]:
                required_fields = ["currency", "home_currency"]
            elif rule.rule_code in ["R010", "R011"]:
                required_fields = ["country_code"]
            elif rule.rule_code == "R012":
                required_fields = ["country_code", "txn_date"]
            elif rule.rule_code == "R013":
                required_fields = ["domestic_status"]
            elif rule.rule_code == "R014":
                required_fields = ["load_source"]
            elif rule.rule_code == "R016":
                required_fields = ["settlement_currency", "originating_country_currency"]

            for field in required_fields:
                if not any(getattr(tx, field, None) not in (None, "") for tx in transactions):
                    missing_fields.append(field)

            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=len(missing_fields) == 0,
                reason="Sufficient data" if len(missing_fields) == 0 else f"Missing fields: {', '.join(missing_fields)}",
                alerts_generated=0,
            ))

        # Disabled rules (R004)
        elif classification == "disabled":
            coverage.append(RuleCoverageItem(
                rule_code=rule.rule_code,
                rule_name=rule.name,
                category=rule.category,
                has_sufficient_data=False,
                reason="Rule is intentionally disabled - insufficient canonical data",
                alerts_generated=0,
            ))

    return coverage
