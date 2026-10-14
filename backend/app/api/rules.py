from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.models.rule_configuration import RuleConfiguration
from backend.app.schemas.rule_configuration import RuleConfigurationPatch, RuleConfigurationRead
from backend.app.schemas.errors import ErrorResponse
from backend.app.services.rule_configuration_service import RuleConfigurationService


router = APIRouter(prefix="/rules", tags=["Rules"])


@router.get(
    "",
    response_model=list[RuleConfigurationRead],
    summary="List rule configurations",
    description="Lists persisted AML rule configurations ordered by priority and rule code.",
)
def list_rules(db: Session = Depends(get_db)):
    RuleConfigurationService.initialize(db)
    return db.query(RuleConfiguration).order_by(
        RuleConfiguration.priority, RuleConfiguration.rule_code
    ).all()


@router.get(
    "/{rule_code}",
    response_model=RuleConfigurationRead,
    summary="Get a rule configuration",
    responses={404: {"model": ErrorResponse, "description": "Rule code was not found."}},
)
def get_rule(rule_code: str, db: Session = Depends(get_db)):
    RuleConfigurationService.initialize(db)
    row = db.query(RuleConfiguration).filter_by(rule_code=rule_code).one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Rule not found")
    return row


@router.patch(
    "/{rule_code}",
    response_model=RuleConfigurationRead,
    summary="Update a rule configuration",
    description="Updates enabled state, priority, risk level, or rule-specific JSON parameters.",
    responses={
        404: {"model": ErrorResponse, "description": "Rule code was not found."},
        422: {"model": ErrorResponse, "description": "Rule configuration validation failed."},
    },
)
def update_rule(
    rule_code: str,
    changes: RuleConfigurationPatch,
    db: Session = Depends(get_db),
):
    try:
        return RuleConfigurationService.update(
            db, rule_code, changes.model_dump(exclude_unset=True)
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Rule not found")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
