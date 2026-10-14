from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    txn_date: datetime | None
    corporate_name: str | None
    proxy_card_number: str | None
    card_number: str | None
    rrn: str | None
    auth_code: str | None
    ext_txn_id: str | None
    amount: float | None
    transaction_type: str | None
    status: str | None
    customer_id: str | None
    post_wallet_balance: float | None
    cr_dr_flag: str | None
    other_party_id: str | None
    other_party_name: str | None
    currency: str | None
    home_currency: str | None
    country_code: str | None
    domestic_status: str | None
    load_source: str | None
    settlement_currency: str | None
    originating_country_currency: str | None
    product: str | None
    txn_amount: float | None
    fees: float | None
    description: str | None
    mcc: str | None
    activation_date: datetime | None


class TransactionListResponse(BaseModel):
    transactions: list[TransactionRead]
    total: int
    page: int
    page_size: int
    total_pages: int


class TransactionAlertSummary(BaseModel):
    id: int
    alert_code: str
    rule_code: str


class TransactionCaseSummary(BaseModel):
    id: int
    case_code: str
    status: str


class TransactionDetail(TransactionRead):
    alert_count: int
    alerts: list[TransactionAlertSummary]
    cases: list[TransactionCaseSummary]


class ValidationResult(BaseModel):
    total_rows: int
    valid_rows: int
    invalid_rows: int
    missing_required_fields: dict[str, int] = {}
    missing_optional_fields: dict[str, int] = {}
    unknown_columns: list[str] = []
    invalid_data_types: dict[str, int] = {}
    invalid_dates: dict[str, int] = {}
    invalid_amounts: int = 0
    unsupported_transaction_types: dict[str, int] = {}
    column_mapping: dict[str, str] = {}


class TransactionImportResponse(BaseModel):
    message: str
    import_id: int
    source_filename: str | None
    rows_processed: int
    records_imported: int
    duplicates_skipped: int
    status: str
    validation: ValidationResult | None = None
