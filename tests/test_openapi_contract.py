from backend.app.main import app


EXPECTED_OPERATIONS = {
    "/": {"get"},
    "/health": {"get"},
    "/transactions": {"get"},
    "/transactions/import": {"post"},
    "/transactions/{transaction_id}": {"get"},
    "/rules": {"get"},
    "/rules/{rule_code}": {"get", "patch"},
    "/alerts": {"get"},
    "/alerts/{alert_id}": {"get"},
    "/alerts/{alert_id}/status": {"patch"},
    "/alerts/{alert_id}/priority": {"patch"},
    "/alerts/{alert_id}/assignment": {"patch"},
    "/alerts/{alert_id}/case": {"post"},
    "/cases": {"get"},
    "/cases/{case_id}": {"get"},
    "/cases/{case_id}/status": {"patch"},
    "/cases/{case_id}/priority": {"patch"},
    "/cases/{case_id}/assignment": {"patch"},
    "/cases/{case_id}/comments": {"get", "post"},
    "/dashboard/summary": {"get"},
    "/dashboard/alerts/trend": {"get"},
    "/dashboard/transactions/trend": {"get"},
    "/dashboard/rules/top": {"get"},
    "/dashboard/distributions": {"get"},
    "/monitoring/run": {"post"},
}


def test_openapi_contains_documented_operations_and_tags():
    schema = app.openapi()

    for path, methods in EXPECTED_OPERATIONS.items():
        assert path in schema["paths"]
        for method in methods:
            operation = schema["paths"][path][method]
            assert operation["summary"]
            assert operation["tags"]

    assert {
        tag["name"] for tag in schema["tags"]
    } >= {"System", "Transactions", "Rules", "Alerts", "Cases", "Dashboard", "Monitoring"}


def test_openapi_contains_major_schemas_and_error_responses():
    schema = app.openapi()
    component_schemas = schema["components"]["schemas"]

    for name in (
        "TransactionListResponse",
        "TransactionDetail",
        "RuleConfigurationPatch",
        "AlertListResponse",
        "CaseDetail",
        "DashboardSummary",
        "MonitoringRunResponse",
        "ErrorResponse",
    ):
        assert name in component_schemas

    assert "ErrorResponse" in str(
        schema["paths"]["/transactions/{transaction_id}"]["get"]["responses"]
    )
    assert "ErrorResponse" in str(
        schema["paths"]["/alerts/{alert_id}/case"]["post"]["responses"]
    )


def test_fastapi_documentation_routes_are_registered():
    route_paths = {
        route.path for route in app.routes if hasattr(route, "path")
    }

    assert "/docs" in route_paths
    assert "/redoc" in route_paths
    assert "/openapi.json" in route_paths
