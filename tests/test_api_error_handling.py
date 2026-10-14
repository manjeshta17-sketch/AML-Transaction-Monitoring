import asyncio

from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi import Request

from backend.app.main import (
    http_error_handler,
    request_validation_handler,
    unexpected_exception_handler,
)
from backend.app.schemas.alert import AlertAssignmentUpdate
from backend.app.schemas.case import CaseAssignmentUpdate


def _request(path: str = "/test") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": path,
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
            "scheme": "http",
        }
    )


def test_http_exception_handler_returns_consistent_not_found_envelope():
    response = asyncio.run(
        http_error_handler(_request("/transactions/999999"), HTTPException(404, "Transaction not found."))
    )

    assert response.status_code == 404
    assert response.body == (
        b'{"error":{"code":"NOT_FOUND","message":"Transaction not found.","details":[]}}'
    )


def test_validation_exception_handler_returns_safe_validation_envelope():
    error = RequestValidationError(
        [{"type": "greater_than", "loc": ("query", "page"), "msg": "Input should be greater than 0"}]
    )
    response = asyncio.run(request_validation_handler(_request(), error))

    assert response.status_code == 422
    assert b"VALIDATION_ERROR" in response.body
    assert b"page" in response.body


def test_unexpected_exception_handler_does_not_expose_exception_details():
    response = asyncio.run(
        unexpected_exception_handler(_request("/broken"), RuntimeError("secret database detail"))
    )

    assert response.status_code == 500
    assert b"INTERNAL_SERVER_ERROR" in response.body
    assert b"secret database detail" not in response.body


def test_assignment_payloads_reject_blank_and_unknown_fields():
    for schema in (AlertAssignmentUpdate, CaseAssignmentUpdate):
        try:
            schema(assigned_to="   ")
            raise AssertionError("blank assignment should be rejected")
        except ValueError:
            pass

        try:
            schema(assigned_to="analyst", unexpected=True)
            raise AssertionError("unknown fields should be rejected")
        except ValueError:
            pass
