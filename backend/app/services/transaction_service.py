from dataclasses import dataclass

import pandas as pd
from sqlalchemy.orm import Session

from backend.app.models.transaction import Transaction
from backend.app.models.transaction_import import TransactionImport


COLUMN_MAPPING = {
    "Txn Date": "txn_date",
    "Corporate Name": "corporate_name",
    "Proxy Card Number": "proxy_card_number",
    "Card Number": "card_number",
    "RRN": "rrn",
    "Auth Code": "auth_code",
    "Ext Txn Id": "ext_txn_id",
    "Amount": "amount",
    "TransactionType": "transaction_type",
    "Status": "status",
    "Customer Id": "customer_id",
    "Post Wallet Balance": "post_wallet_balance",
    "CR/DR Flag": "cr_dr_flag",
    "Other Party Id": "other_party_id",
    "Other Party Name": "other_party_name",
    "Currency": "currency",
    "Product": "product",
    "Txn Amount": "txn_amount",
    "Fees": "fees",
    "Description": "description",
    "mcc": "mcc",
    "ActivationDate": "activation_date",
}

REQUIRED_COLUMNS = tuple(COLUMN_MAPPING)
OPTIONAL_COLUMN_MAPPING = {
    "Home Currency": "home_currency",
    "Country Code": "country_code",
    "Domestic Status": "domestic_status",
    "Load Source": "load_source",
    "Settlement Currency": "settlement_currency",
    "Originating Country Currency": "originating_country_currency",
}


@dataclass(frozen=True)
class ImportResult:
    import_id: int
    source_filename: str | None
    rows_processed: int
    records_imported: int
    duplicates_skipped: int
    status: str


def import_transactions(
    file_path: str,
    db: Session,
    *,
    source_filename: str | None = None,
    detailed: bool = False,
) -> int | ImportResult:
    """Import one transaction-report CSV and return the rows newly inserted."""
    transaction_import = TransactionImport(
        source_filename=source_filename,
        status="PROCESSING",
    )
    db.add(transaction_import)
    db.flush()
    try:
        # Transaction reports begin with a title and report-date line. The third
        # line is the pipe-delimited header row.
        df = pd.read_csv(
            file_path,
            sep="|",
            skiprows=2,
            dtype=str,
        )
    except (OSError, pd.errors.ParserError) as error:
        transaction_import.status = "FAILED"
        db.commit()
        raise ValueError(f"Unable to read transaction CSV: {error}") from error

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in df.columns]
    if missing_columns:
        transaction_import.status = "FAILED"
        transaction_import.rows_processed = len(df.index)
        db.commit()
        raise ValueError(
            "Transaction CSV is missing required columns: "
            + ", ".join(missing_columns)
        )

    # Select the known report fields before renaming so an unexpected column is
    # never passed into the ORM mapping.
    selected_columns = list(REQUIRED_COLUMNS) + [
        column for column in OPTIONAL_COLUMN_MAPPING if column in df.columns
    ]
    df = df.loc[:, selected_columns].rename(
        columns={**COLUMN_MAPPING, **OPTIONAL_COLUMN_MAPPING}
    )
    for column in OPTIONAL_COLUMN_MAPPING.values():
        if column not in df:
            df[column] = None

    numeric_columns = [
        "amount",
        "post_wallet_balance",
        "txn_amount",
        "fees"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    date_columns = [
        "txn_date",
        "activation_date"
    ]

    for column in date_columns:
        df[column] = pd.to_datetime(
            df[column],
            errors="coerce"
        )

    # Convert pandas missing values (including invalid numeric/date values) to
    # SQL NULL rather than leaking NaN/NaT through to SQLAlchemy.
    df = df.astype(object).where(pd.notna(df), None)

    existing_transaction_ids = {
        transaction_id
        for (transaction_id,) in db.query(Transaction.ext_txn_id)
        .filter(Transaction.ext_txn_id.isnot(None))
        .all()
        if transaction_id
    }

    records = []
    imported_transaction_ids = set()
    duplicates_skipped = 0
    for record in df.to_dict(orient="records"):
        transaction_id = record["ext_txn_id"]
        if transaction_id and (
            transaction_id in existing_transaction_ids
            or transaction_id in imported_transaction_ids
        ):
            duplicates_skipped += 1
            continue

        record["import_id"] = transaction_import.id
        records.append(record)
        if transaction_id:
            imported_transaction_ids.add(transaction_id)

    try:
        if records:
            db.bulk_insert_mappings(Transaction, records)
        transaction_import.rows_processed = len(df.index)
        transaction_import.imported_count = len(records)
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
        records_imported=len(records),
        duplicates_skipped=duplicates_skipped,
        status="COMPLETED",
    )
    return result if detailed else len(records)
