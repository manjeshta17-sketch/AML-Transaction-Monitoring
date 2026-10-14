"""Tests for enhanced transaction import with CSV/XLS/XLSX support and validation."""

import pytest
from io import BytesIO
from sqlalchemy.orm import Session

from backend.app.services.transaction_service_enhanced import (
    detect_file_type,
    map_columns,
    read_file,
    ValidationResult,
    import_transactions_enhanced,
)


def test_detect_file_type_csv():
    """Test CSV file type detection."""
    assert detect_file_type("test.csv") == "csv"
    assert detect_file_type("test.CSV") == "csv"


def test_detect_file_type_excel():
    """Test Excel file type detection."""
    assert detect_file_type("test.xls") == "excel"
    assert detect_file_type("test.xlsx") == "excel"
    assert detect_file_type("test.XLSX") == "excel"


def test_detect_file_type_unsupported():
    """Test unsupported file type raises error."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        detect_file_type("test.txt")


def test_read_file_detects_pipe_delimited_report_with_metadata(tmp_path):
    """Native pipe reports can include leading metadata before their header."""
    report = tmp_path / "native_transaction_report.csv"
    report.write_text(
        "Report Name|Transaction Report\n"
        "Period|2026-01-01 to 2026-01-31\n"
        "Txn Date|Corporate Name|Card Number|RRN|Auth Code|Ext Txn Id|Amount|TransactionType|Status|Customer Id\n"
        "2026-01-03|Demo Corp|411111|RRN-1|AUTH-1|EXT-1|150.50|POS|PAYMENT_SUCCESS|CUST-1\n",
        encoding="utf-8",
    )

    dataframe = read_file(str(report), "csv")

    assert dataframe.columns.tolist() == [
        "Txn Date", "Corporate Name", "Card Number", "RRN", "Auth Code",
        "Ext Txn Id", "Amount", "TransactionType", "Status", "Customer Id",
    ]
    assert len(dataframe.index) == 1


def test_map_columns_standard_names():
    """Test column mapping with standard column names."""
    import pandas as pd

    df = pd.DataFrame({
        "Txn Date": ["2024-01-01"],
        "Amount": [100.0],
        "Card Number": ["1234"],
        "Customer Id": ["CUST001"],
        "Status": ["PAYMENT_SUCCESS"],
        "TransactionType": ["LOAD"],
        "RRN": ["RRN001"],
        "Auth Code": ["AUTH001"],
        "Ext Txn Id": ["EXT001"],
        "Corporate Name": ["Corp"],
    })

    mapping, unknown, missing = map_columns(df)

    assert mapping["Txn Date"] == "txn_date"
    assert mapping["Amount"] == "amount"
    assert mapping["Card Number"] == "card_number"
    assert len(unknown) == 0
    assert len(missing) == 0


def test_map_columns_alternative_names():
    """Test column mapping with alternative column names."""
    import pandas as pd

    df = pd.DataFrame({
        "Transaction Date": ["2024-01-01"],
        "amount": [100.0],
        "Card": ["1234"],
        "Customer ID": ["CUST001"],
        "status": ["PAYMENT_SUCCESS"],
        "Type": ["LOAD"],
        "RRN": ["RRN001"],
        "Authorization Code": ["AUTH001"],
        "Transaction ID": ["EXT001"],
        "Corporate": ["Corp"],
    })

    mapping, unknown, missing = map_columns(df)

    assert mapping["Transaction Date"] == "txn_date"
    assert mapping["amount"] == "amount"
    assert mapping["Card"] == "card_number"
    assert len(unknown) == 0
    assert len(missing) == 0


def test_map_columns_missing_required():
    """Test column mapping with missing required columns."""
    import pandas as pd

    df = pd.DataFrame({
        "Txn Date": ["2024-01-01"],
        "Amount": [100.0],
        # Missing Card Number, Customer Id, etc.
    })

    mapping, unknown, missing = map_columns(df)

    assert len(missing) > 0
    assert "card_number" in missing


def test_map_columns_unknown_columns():
    """Test column mapping identifies unknown columns."""
    import pandas as pd

    df = pd.DataFrame({
        "Txn Date": ["2024-01-01"],
        "Amount": [100.0],
        "UnknownColumn": ["value"],
        "AnotherUnknown": ["value2"],
    })

    mapping, unknown, missing = map_columns(df)

    assert len(unknown) == 2
    assert "UnknownColumn" in unknown
    assert "AnotherUnknown" in unknown


def test_validation_result_creation():
    """Test ValidationResult dataclass creation."""
    validation = ValidationResult(
        total_rows=100,
        valid_rows=95,
        invalid_rows=5,
        missing_required_fields={"card_number": 3},
        missing_optional_fields={"home_currency": 10},
        unknown_columns=["ExtraColumn"],
        invalid_data_types={},
        invalid_dates={},
        invalid_amounts=2,
        unsupported_transaction_types={},
        column_mapping={"Txn Date": "txn_date"},
    )

    assert validation.total_rows == 100
    assert validation.valid_rows == 95
    assert validation.invalid_rows == 5
    assert validation.missing_required_fields["card_number"] == 3
    assert validation.invalid_amounts == 2


@pytest.mark.integration
def test_import_csv_with_validation(tmp_path, db_session: Session):
    """Test CSV import with validation using a temporary file."""
    import pandas as pd

    # Create a test CSV file
    csv_file = tmp_path / "test_transactions.csv"
    df = pd.DataFrame({
        "Txn Date": ["2024-01-01", "2024-01-02"],
        "Amount": [100.0, 200.0],
        "Card Number": ["1234", "5678"],
        "Customer Id": ["CUST001", "CUST002"],
        "Status": ["PAYMENT_SUCCESS", "PAYMENT_SUCCESS"],
        "TransactionType": ["LOAD", "LOAD"],
        "RRN": ["RRN001", "RRN002"],
        "Auth Code": ["AUTH001", "AUTH002"],
        "Ext Txn Id": ["EXT001", "EXT002"],
        "Corporate Name": ["Corp1", "Corp2"],
    })
    df.to_csv(csv_file, index=False)

    # Import with detailed validation
    result = import_transactions_enhanced(
        str(csv_file),
        db_session,
        source_filename="test_transactions.csv",
        detailed=True,
    )

    assert result.status == "COMPLETED"
    assert result.rows_processed == 2
    assert result.records_imported == 2
    assert result.validation is not None
    assert result.validation.total_rows == 2
    assert result.validation.valid_rows == 2
    assert result.validation.invalid_rows == 0


@pytest.mark.integration
def test_import_excel_with_validation(tmp_path, db_session: Session):
    """Test Excel import with validation using a temporary file."""
    import pandas as pd
    pytest.importorskip("openpyxl")

    # Create a test Excel file
    excel_file = tmp_path / "test_transactions.xlsx"
    df = pd.DataFrame({
        "Txn Date": ["2024-01-01", "2024-01-02"],
        "Amount": [100.0, 200.0],
        "Card Number": ["1234", "5678"],
        "Customer Id": ["CUST001", "CUST002"],
        "Status": ["PAYMENT_SUCCESS", "PAYMENT_SUCCESS"],
        "TransactionType": ["LOAD", "LOAD"],
        "RRN": ["RRN001", "RRN002"],
        "Auth Code": ["AUTH001", "AUTH002"],
        "Ext Txn Id": ["EXT001", "EXT002"],
        "Corporate Name": ["Corp1", "Corp2"],
    })
    df.to_excel(excel_file, index=False)

    # Import with detailed validation
    result = import_transactions_enhanced(
        str(excel_file),
        db_session,
        source_filename="test_transactions.xlsx",
        detailed=True,
    )

    assert result.status == "COMPLETED"
    assert result.rows_processed == 2
    assert result.records_imported == 2
    assert result.validation is not None


@pytest.mark.integration
def test_import_with_missing_required_columns(tmp_path, db_session: Session):
    """Test import fails with missing required columns."""
    import pandas as pd

    # Create a CSV missing required columns
    csv_file = tmp_path / "incomplete_transactions.csv"
    df = pd.DataFrame({
        "Txn Date": ["2024-01-01"],
        "Amount": [100.0],
        # Missing Card Number, Customer Id, etc.
    })
    df.to_csv(csv_file, index=False)

    # Import should fail
    with pytest.raises(ValueError, match="missing required columns"):
        import_transactions_enhanced(
            str(csv_file),
            db_session,
            source_filename="incomplete_transactions.csv",
            detailed=True,
        )


@pytest.mark.integration
def test_import_duplicate_detection(tmp_path, db_session: Session):
    """Test that duplicate transactions are skipped."""
    import pandas as pd

    # Create a CSV with duplicate ext_txn_id
    csv_file = tmp_path / "duplicate_transactions.csv"
    df = pd.DataFrame({
        "Txn Date": ["2024-01-01", "2024-01-02"],
        "Amount": [100.0, 200.0],
        "Card Number": ["1234", "5678"],
        "Customer Id": ["CUST001", "CUST002"],
        "Status": ["PAYMENT_SUCCESS", "PAYMENT_SUCCESS"],
        "TransactionType": ["LOAD", "LOAD"],
        "RRN": ["RRN001", "RRN002"],
        "Auth Code": ["AUTH001", "AUTH002"],
        "Ext Txn Id": ["EXT001", "EXT001"],  # Duplicate
        "Corporate Name": ["Corp1", "Corp2"],
    })
    df.to_csv(csv_file, index=False)

    # Import
    result = import_transactions_enhanced(
        str(csv_file),
        db_session,
        source_filename="duplicate_transactions.csv",
        detailed=True,
    )

    assert result.status == "COMPLETED"
    assert result.rows_processed == 2
    assert result.duplicates_skipped == 1
    assert result.records_imported == 1


@pytest.mark.integration
def test_import_rejects_rows_with_invalid_amount_or_required_value(tmp_path, db_session: Session):
    """Malformed values are reported and excluded instead of being imported as nulls."""
    report = tmp_path / "invalid_rows.csv"
    report.write_text(
        "Txn Date,Corporate Name,Card Number,RRN,Auth Code,Ext Txn Id,Amount,TransactionType,Status,Customer Id\n"
        "2026-01-03,Demo Corp,411111,RRN-1,AUTH-1,EXT-1,not-a-number,POS,PAYMENT_SUCCESS,CUST-1\n"
        "2026-01-04,Demo Corp,411112,RRN-2,AUTH-2,EXT-2,100.00,POS,PAYMENT_SUCCESS,CUST-2\n",
        encoding="utf-8",
    )

    result = import_transactions_enhanced(str(report), db_session, detailed=True)

    assert result.records_imported == 1
    assert result.validation is not None
    assert result.validation.invalid_rows == 1
    assert result.validation.invalid_amounts == 1
