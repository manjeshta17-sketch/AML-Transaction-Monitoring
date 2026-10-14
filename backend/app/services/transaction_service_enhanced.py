"""Enhanced transaction import service supporting CSV, XLS, XLSX with validation."""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.models.transaction import Transaction
from backend.app.models.transaction_import import TransactionImport


# Flexible column mapping - multiple possible names for each field
COLUMN_ALIASES = {
    "txn_date": ["Txn Date", "Transaction Date", "Date", "txn_date"],
    "corporate_name": ["Corporate Name", "Corporate", "corporate_name"],
    "proxy_card_number": ["Proxy Card Number", "Proxy Card", "proxy_card_number"],
    "card_number": ["Card Number", "Card", "card_number"],
    "rrn": ["RRN", "rrn"],
    "auth_code": ["Auth Code", "Authorization Code", "auth_code"],
    "ext_txn_id": ["Ext Txn Id", "External Transaction ID", "Transaction ID", "ext_txn_id"],
    "amount": ["Amount", "amount"],
    "transaction_type": ["TransactionType", "Transaction Type", "Type", "transaction_type"],
    "status": ["Status", "status"],
    "customer_id": ["Customer Id", "Customer ID", "customer_id"],
    "post_wallet_balance": ["Post Wallet Balance", "Wallet Balance", "post_wallet_balance"],
    "cr_dr_flag": ["CR/DR Flag", "cr_dr_flag"],
    "other_party_id": ["Other Party Id", "Other Party ID", "other_party_id"],
    "other_party_name": ["Other Party Name", "other_party_name"],
    "currency": ["Currency", "currency"],
    "product": ["Product", "product"],
    "txn_amount": ["Txn Amount", "Transaction Amount", "txn_amount"],
    "fees": ["Fees", "fees"],
    "description": ["Description", "description"],
    "mcc": ["mcc", "MCC"],
    "activation_date": ["ActivationDate", "Activation Date", "activation_date"],
    "home_currency": ["Home Currency", "home_currency"],
    "country_code": ["Country Code", "country_code"],
    "domestic_status": ["Domestic Status", "domestic_status"],
    "load_source": ["Load Source", "load_source"],
    "settlement_currency": ["Settlement Currency", "settlement_currency"],
    "originating_country_currency": ["Originating Country Currency", "originating_country_currency"],
}

# Required fields for import
REQUIRED_FIELDS = {
    "txn_date", "corporate_name", "card_number", "rrn", "auth_code",
    "ext_txn_id", "amount", "transaction_type", "status", "customer_id"
}

# Optional fields
OPTIONAL_FIELDS = {
    "proxy_card_number", "post_wallet_balance", "cr_dr_flag",
    "other_party_id", "other_party_name", "currency", "product",
    "txn_amount", "fees", "description", "mcc", "activation_date",
    "home_currency", "country_code", "domestic_status", "load_source",
    "settlement_currency", "originating_country_currency"
}

# Valid transaction types
VALID_TRANSACTION_TYPES = {"LOAD", "POS", "ATM", "ECOM", "CARD_TO_CARD"}

# Valid statuses
VALID_STATUSES = {"PAYMENT_SUCCESS", "REVERSED", "DECLINED"}

CSV_DELIMITERS = ("|", ",", ";", "\t")
HEADER_SCAN_ROWS = 25


@dataclass(frozen=True)
class ValidationResult:
    """Detailed validation result for transaction import."""
    total_rows: int
    valid_rows: int
    invalid_rows: int
    missing_required_fields: dict[str, int] = field(default_factory=dict)
    missing_optional_fields: dict[str, int] = field(default_factory=dict)
    unknown_columns: list[str] = field(default_factory=list)
    invalid_data_types: dict[str, int] = field(default_factory=dict)
    invalid_dates: dict[str, int] = field(default_factory=dict)
    invalid_amounts: int = 0
    unsupported_transaction_types: dict[str, int] = field(default_factory=dict)
    column_mapping: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ImportResult:
    """Enhanced import result with validation details."""
    import_id: int
    source_filename: str | None
    rows_processed: int
    records_imported: int
    duplicates_skipped: int
    status: str
    validation: ValidationResult | None = None


def detect_file_type(file_path: str) -> str:
    """Detect file type from extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix == ".csv":
        return "csv"
    elif suffix in [".xls", ".xlsx"]:
        return "excel"
    else:
        raise ValueError(f"Unsupported file type: {suffix}. Supported formats: CSV, XLS, XLSX")


def _header_score(values: list[object]) -> int:
    """Return how closely a row resembles a supported transaction header."""
    aliases = {alias.casefold() for names in COLUMN_ALIASES.values() for alias in names}
    return sum(str(value).strip().casefold() in aliases for value in values)


def _detect_csv_header(file_path: str) -> tuple[str, int]:
    """Find the CSV delimiter and header row without assuming a report layout."""
    best_delimiter, best_row, best_score = ",", 0, -1
    with Path(file_path).open("r", encoding="utf-8-sig", errors="replace") as source:
        for row_index, line in enumerate(source):
            if row_index >= HEADER_SCAN_ROWS:
                break
            for delimiter in CSV_DELIMITERS:
                score = _header_score(line.rstrip("\r\n").split(delimiter))
                if score > best_score:
                    best_delimiter, best_row, best_score = delimiter, row_index, score
    return best_delimiter, best_row


def _detect_excel_header(file_path: str) -> int:
    """Find the header row in an Excel report, including reports with metadata rows."""
    preview = pd.read_excel(file_path, header=None, nrows=HEADER_SCAN_ROWS, dtype=str)
    scores = [_header_score(row.tolist()) for _, row in preview.iterrows()]
    return scores.index(max(scores)) if scores else 0


def read_file(file_path: str, file_type: str, skiprows: int = 0) -> pd.DataFrame:
    """Read CSV or Excel reports, automatically locating the transaction header."""
    try:
        if file_type == "csv":
            delimiter, detected_header_row = _detect_csv_header(file_path)
            header_row = skiprows if skiprows > 0 else detected_header_row
            return pd.read_csv(file_path, sep=delimiter, skiprows=header_row, dtype=str)
        elif file_type == "excel":
            header_row = skiprows if skiprows > 0 else _detect_excel_header(file_path)
            return pd.read_excel(file_path, skiprows=header_row, dtype=str)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")
    except Exception as error:
        raise ValueError(f"Unable to read file: {error}") from error


def map_columns(df: pd.DataFrame) -> tuple[dict[str, str], list[str], list[str]]:
    """
    Map file columns to standard field names using aliases.
    Returns (mapping, unknown_columns, missing_required_fields)
    """
    file_columns = {col.strip() for col in df.columns}
    mapping = {}
    unknown_columns = []
    missing_required = []

    # Map each standard field to the first matching alias in the file
    for standard_field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in file_columns:
                mapping[alias] = standard_field
                break
        else:
            # No alias found - check if required
            if standard_field in REQUIRED_FIELDS:
                missing_required.append(standard_field)

    # Identify unknown columns (columns in file that don't map to any field)
    all_aliases = {alias for aliases in COLUMN_ALIASES.values() for alias in aliases}
    unknown_columns = [col for col in df.columns if col.strip() not in all_aliases]

    return mapping, unknown_columns, missing_required


def validate_row(row: dict[str, Any], mapping: dict[str, str]) -> dict[str, Any]:
    """Validate a single row and return validation errors."""
    errors = {}

    # Map to standard field names
    mapped_row = {mapping.get(k, k): v for k, v in row.items()}

    # Check required fields
    for field in REQUIRED_FIELDS:
        if field not in mapped_row or pd.isna(mapped_row[field]) or str(mapped_row[field]).strip() == "":
            errors.setdefault("missing_required", {})[field] = errors.get("missing_required", {}).get(field, 0) + 1

    # Validate transaction type
    if "transaction_type" in mapped_row and pd.notna(mapped_row["transaction_type"]):
        tx_type = str(mapped_row["transaction_type"]).strip().upper()
        if tx_type not in VALID_TRANSACTION_TYPES:
            errors.setdefault("invalid_transaction_types", {})[tx_type] = errors.get("invalid_transaction_types", {}).get(tx_type, 0) + 1

    # Validate status
    if "status" in mapped_row and pd.notna(mapped_row["status"]):
        status = str(mapped_row["status"]).strip().upper()
        if status not in VALID_STATUSES:
            errors.setdefault("invalid_statuses", {})[status] = errors.get("invalid_statuses", {}).get(status, 0) + 1

    return errors


def import_transactions_enhanced(
    file_path: str,
    db: Session,
    *,
    source_filename: str | None = None,
    detailed: bool = False,
    skiprows: int = 0,
) -> int | ImportResult:
    """
    Enhanced transaction import supporting CSV, XLS, XLSX with validation.
    Returns ImportResult with detailed validation when detailed=True.
    """
    transaction_import = TransactionImport(
        source_filename=source_filename,
        status="PROCESSING",
    )
    db.add(transaction_import)
    db.flush()

    try:
        # Detect file type
        file_type = detect_file_type(file_path)

        # Read file
        df = read_file(file_path, file_type, skiprows=skiprows)

        # Normalize source headers before alias matching.
        df = df.rename(columns=lambda column: str(column).strip())

        # Map columns
        column_mapping, unknown_columns, missing_required_fields = map_columns(df)

        if missing_required_fields:
            transaction_import.status = "FAILED"
            transaction_import.rows_processed = len(df.index)
            db.commit()
            raise ValueError(
                f"File is missing required columns: {', '.join(missing_required_fields)}"
            )

        # Rename columns to standard names
        df = df.rename(columns=column_mapping)

        # Keep only known columns
        known_columns = list(REQUIRED_FIELDS) + list(OPTIONAL_FIELDS)
        available_columns = [col for col in known_columns if col in df.columns]
        df = df[available_columns]

        # Type conversion and validation.  Preserve conversion failures so they
        # are reported as invalid values rather than silently becoming nulls.
        numeric_columns = ["amount", "post_wallet_balance", "txn_amount", "fees"]
        invalid_numeric_masks: dict[str, pd.Series] = {}
        for col in numeric_columns:
            if col in df.columns:
                raw_values = df[col]
                converted = pd.to_numeric(raw_values, errors="coerce")
                invalid_numeric_masks[col] = (
                    raw_values.notna()
                    & raw_values.astype(str).str.strip().ne("")
                    & converted.isna()
                )
                df[col] = converted

        date_columns = ["txn_date", "activation_date"]
        invalid_date_masks: dict[str, pd.Series] = {}
        for col in date_columns:
            if col in df.columns:
                raw_values = df[col]
                converted = pd.to_datetime(raw_values, errors="coerce")
                invalid_date_masks[col] = (
                    raw_values.notna()
                    & raw_values.astype(str).str.strip().ne("")
                    & converted.isna()
                )
                df[col] = converted

        # Convert NaN/NaT to None
        df = df.astype(object).where(pd.notna(df), None)

        # Validate each row
        valid_records = []
        invalid_amounts = 0
        invalid_dates: dict[str, int] = {}
        invalid_data_types: dict[str, int] = {}
        missing_required_counts: dict[str, int] = {}
        unsupported_transaction_types: dict[str, int] = {}
        valid_rows = 0
        invalid_rows = 0
        missing_optional_counts = {field: 0 for field in OPTIONAL_FIELDS}

        for idx, row in df.iterrows():
            row_data = row.to_dict()
            row_errors = validate_row(row_data, {})
            row_has_error = bool(row_errors)

            for field, count in row_errors.get("missing_required", {}).items():
                missing_required_counts[field] = missing_required_counts.get(field, 0) + count
            for value, count in row_errors.get("invalid_transaction_types", {}).items():
                unsupported_transaction_types[value] = unsupported_transaction_types.get(value, 0) + count
            for value, count in row_errors.get("invalid_statuses", {}).items():
                invalid_data_types["status"] = invalid_data_types.get("status", 0) + count
            for col, mask in invalid_numeric_masks.items():
                if bool(mask.loc[idx]):
                    invalid_amounts += 1
                    row_has_error = True
            for col, mask in invalid_date_masks.items():
                if bool(mask.loc[idx]):
                    invalid_dates[col] = invalid_dates.get(col, 0) + 1
                    row_has_error = True

            # Check optional fields missing
            for field in OPTIONAL_FIELDS:
                if field in row and (row[field] is None or str(row[field]).strip() == ""):
                    missing_optional_counts[field] += 1

            if not row_has_error:
                valid_records.append(row_data)
                valid_rows += 1
            else:
                invalid_rows += 1

        validation = ValidationResult(
            total_rows=len(df.index),
            valid_rows=valid_rows,
            invalid_rows=invalid_rows,
            missing_required_fields=missing_required_counts,
            missing_optional_fields={k: v for k, v in missing_optional_counts.items() if v > 0},
            unknown_columns=unknown_columns,
            invalid_data_types=invalid_data_types,
            invalid_dates=invalid_dates,
            invalid_amounts=invalid_amounts,
            unsupported_transaction_types=unsupported_transaction_types,
            column_mapping=column_mapping,
        )

        # Check for duplicates
        existing_transaction_ids = {
            tx_id for (tx_id,) in db.query(Transaction.ext_txn_id)
            .filter(Transaction.ext_txn_id.isnot(None))
            .all()
            if tx_id
        }

        records_to_import = []
        imported_transaction_ids = set()
        duplicates_skipped = 0

        for record in valid_records:
            tx_id = record.get("ext_txn_id")
            if tx_id and (tx_id in existing_transaction_ids or tx_id in imported_transaction_ids):
                duplicates_skipped += 1
                continue

            record["import_id"] = transaction_import.id
            records_to_import.append(record)
            if tx_id:
                imported_transaction_ids.add(tx_id)

        # Import valid records
        try:
            if records_to_import:
                db.bulk_insert_mappings(Transaction, records_to_import)
            transaction_import.rows_processed = len(df.index)
            transaction_import.imported_count = len(records_to_import)
            transaction_import.duplicate_count = duplicates_skipped
            transaction_import.status = "COMPLETED"
            db.commit()
        except Exception:
            db.rollback()
            raise

        result = ImportResult(
            import_id=transaction_import.id,
            source_filename=source_filename,
            rows_processed=len(df.index),
            records_imported=len(records_to_import),
            duplicates_skipped=duplicates_skipped,
            status="COMPLETED",
            validation=validation if detailed else None,
        )

        return result if detailed else len(records_to_import)

    except Exception as error:
        transaction_import.status = "FAILED"
        if hasattr(transaction_import, 'rows_processed'):
            transaction_import.rows_processed = len(df.index) if 'df' in locals() else 0
        db.commit()
        raise ValueError(f"Transaction import failed: {error}") from error
