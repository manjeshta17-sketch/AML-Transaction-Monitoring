"""Persistence and validation for rule configuration.

The service is intentionally an adapter: the rule engine continues to consume
the existing immutable RuleDefinition contract.
"""

from typing import Any

from sqlalchemy.orm import Session

from backend.app.models.rule_configuration import RuleConfiguration
from backend.app.schemas.rule import RuleDefinition
from backend.app.services.rule_engine import DEFAULT_RULES


_PARAMETER_RULES: dict[str, dict[str, tuple[type, ...]]] = {
    "R001": {"transaction_type": (str,), "amount_threshold": (int, float)},
    "R002": {
        "merchant_field": (str,), "count_threshold": (int,),
        "time_window_minutes": (int, float), "qualifying_statuses": (list,),
        "qualifying_transaction_type_suffixes": (list,),
    },
    "R003": {
        "merchant_field": (str,), "count_threshold": (int,),
        "time_window_minutes": (int, float), "qualifying_statuses": (list,),
    },
    "R004": {
        "implementation_status": (str,), "required_data": (str,), "status_mapping": (str,),
    },
    "R005": {"grouping_field": (str,), "lookback_months": (int,), "increase_percentage": (int, float)},
    "R006": {"grouping_field": (str,), "lookback_months": (int,), "increase_percentage": (int, float)},
    "R007": {"grouping_field": (str,), "lookback_months": (int,), "increase_percentage": (int, float)},
    "R008": {"transaction_type": (str,), "amount_threshold": (int, float), "home_currency_field": (str,)},
    "R009": {"transaction_type": (str,), "amount_threshold": (int, float), "home_currency_field": (str,)},
    "R010": {"transaction_type": (str,), "country_field": (str,), "high_risk_countries": (list,)},
    "R011": {"transaction_type": (str,), "country_field": (str,), "high_risk_countries": (list,)},
    "R012": {"grouping_field": (str,), "country_field": (str,), "time_window_hours": (int, float)},
    "R013": {
        "transaction_type": (str,), "grouping_field": (str,), "lookback_months": (int,),
        "increase_percentage": (int, float), "domestic_field": (str,), "domestic_values": (list,),
    },
    "R014": {
        "grouping_field": (str,), "lookback_months": (int,), "load_source_field": (str,),
        "c2c_source_values": (list,),
    },
    "R015": {"transaction_type": (str,), "amount_threshold": (int, float)},
    "R016": {"settlement_currency_field": (str,), "originating_country_currency_field": (str,)},
}


def _json_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    """Return JSON-safe values without allowing executable configuration."""
    if not isinstance(parameters, dict):
        raise ValueError("Rule parameters must be a JSON object.")
    try:
        import json
        return json.loads(json.dumps(parameters))
    except (TypeError, ValueError) as exc:
        raise ValueError("Rule parameters must contain only JSON-serializable values.") from exc


class RuleConfigurationService:
    @staticmethod
    def _defaults_by_code() -> dict[str, RuleDefinition]:
        return {rule.rule_code: rule for rule in DEFAULT_RULES}

    @classmethod
    def validate_definition(cls, definition: RuleDefinition) -> RuleDefinition:
        defaults = cls._defaults_by_code()
        if definition.rule_code not in defaults:
            raise ValueError(f"Unknown rule code: {definition.rule_code}")
        if definition.priority < 1:
            raise ValueError("Rule priority must be at least 1.")
        if definition.risk_level not in {"low", "medium", "high", "critical"}:
            raise ValueError("Rule risk_level must be low, medium, high, or critical.")

        parameters = _json_parameters(dict(definition.parameters))
        expected = _PARAMETER_RULES[definition.rule_code]
        unknown = set(parameters) - set(expected)
        if unknown:
            raise ValueError(
                f"Unsupported parameters for {definition.rule_code}: {sorted(unknown)}"
            )
        missing = set(expected) - set(parameters)
        if missing:
            raise ValueError(
                f"Missing parameters for {definition.rule_code}: {sorted(missing)}"
            )
        for name, types in expected.items():
            value = parameters[name]
            if not isinstance(value, types) or isinstance(value, bool):
                raise ValueError(f"Invalid type for {definition.rule_code}.{name}.")
            if name in {
                "qualifying_statuses",
                "qualifying_transaction_type_suffixes",
                "high_risk_countries",
                "domestic_values",
                "c2c_source_values",
            } and not all(isinstance(item, str) for item in value):
                raise ValueError(f"{definition.rule_code}.{name} must be a list of strings.")

        # These fields are used as model attribute names or bounded rule inputs.
        constrained_fields = {
            "merchant_field": {"other_party_id", "other_party_name"},
            "grouping_field": {"card_number", "customer_id"},
            "home_currency_field": {"home_currency"},
            "country_field": {"country_code"},
            "domestic_field": {"domestic_status"},
            "load_source_field": {"load_source"},
            "settlement_currency_field": {"settlement_currency"},
            "originating_country_currency_field": {"originating_country_currency"},
        }
        for name, allowed in constrained_fields.items():
            if name in parameters and parameters[name] not in allowed:
                raise ValueError(f"Unsupported field for {definition.rule_code}.{name}.")
        for name in ("count_threshold", "lookback_months", "time_window_minutes", "time_window_hours"):
            if name in parameters and parameters[name] <= 0:
                raise ValueError(f"{name} must be greater than zero.")
        if "increase_percentage" in parameters and parameters["increase_percentage"] < 0:
            raise ValueError("increase_percentage must not be negative.")
        if "amount_threshold" in parameters and parameters["amount_threshold"] < 0:
            raise ValueError("amount_threshold must not be negative.")
        return RuleDefinition(
            rule_code=definition.rule_code,
            name=definition.name,
            description=definition.description,
            category=definition.category,
            risk_level=definition.risk_level,
            priority=definition.priority,
            enabled=bool(definition.enabled),
            parameters=parameters,
        )

    @classmethod
    def initialize(cls, db: Session) -> None:
        existing = {
            row.rule_code for row in db.query(RuleConfiguration).all()
        }
        for default in DEFAULT_RULES:
            if default.rule_code in existing:
                continue
            definition = cls.validate_definition(
                RuleDefinition(
                    **{**default.__dict__, "parameters": cls._json_defaults(default.parameters)}
                )
            )
            db.add(cls._to_model(definition))
        db.commit()

    @staticmethod
    def _json_defaults(parameters: Any) -> dict[str, Any]:
        return {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in dict(parameters).items()
        }

    @staticmethod
    def _to_model(definition: RuleDefinition) -> RuleConfiguration:
        return RuleConfiguration(
            rule_code=definition.rule_code,
            name=definition.name,
            description=definition.description,
            enabled=definition.enabled,
            category=definition.category,
            risk_level=definition.risk_level,
            priority=definition.priority,
            parameters=dict(definition.parameters),
        )

    @classmethod
    def load_rules(cls, db: Session) -> tuple[RuleDefinition, ...]:
        cls.initialize(db)
        rows = db.query(RuleConfiguration).order_by(RuleConfiguration.priority, RuleConfiguration.rule_code).all()
        return tuple(
            cls.validate_definition(
                RuleDefinition(
                    rule_code=row.rule_code, name=row.name, description=row.description,
                    category=row.category, risk_level=row.risk_level, priority=row.priority,
                    enabled=row.enabled, parameters=row.parameters,
                )
            )
            for row in rows
        )

    @classmethod
    def update(
        cls, db: Session, rule_code: str, changes: dict[str, Any]
    ) -> RuleConfiguration:
        cls.initialize(db)
        row = db.query(RuleConfiguration).filter_by(rule_code=rule_code).one_or_none()
        if row is None:
            raise KeyError(rule_code)
        candidate = RuleDefinition(
            rule_code=row.rule_code,
            name=row.name,
            description=row.description,
            category=row.category,
            risk_level=changes.get("risk_level", row.risk_level),
            priority=changes.get("priority", row.priority),
            enabled=changes.get("enabled", row.enabled),
            parameters={
                **dict(row.parameters or {}),
                **(changes.get("parameters") or {}),
            },
        )
        validated = cls.validate_definition(candidate)
        row.enabled = validated.enabled
        row.priority = validated.priority
        row.risk_level = validated.risk_level
        row.parameters = dict(validated.parameters)
        db.commit()
        db.refresh(row)
        return row
