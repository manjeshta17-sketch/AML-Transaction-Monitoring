from datetime import datetime, timedelta
from math import ceil
from pathlib import Path
from tempfile import NamedTemporaryFile

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import String, asc, cast, desc, or_
from sqlalchemy.orm import Session

from backend.app.api.dependencies import get_db
from backend.app.models.alert import Alert
from backend.app.models.case import Case
from backend.app.models.transaction import Transaction
from backend.app.schemas.transaction import (
    TransactionAlertSummary,
    TransactionCaseSummary,
    TransactionDetail,
    TransactionImportResponse,
    TransactionListResponse,
    TransactionRead,
)
from backend.app.schemas.ai_enrichment import AIEnrichmentRead
from backend.app.schemas.errors import ErrorResponse
from backend.app.services.transaction_service import import_transactions
from backend.app.services.transaction_service_enhanced import import_transactions_enhanced


ALLOWED_IMPORT_SUFFIXES = {".csv", ".xls", ".xlsx"}
MAX_IMPORT_FILE_SIZE_BYTES = 25 * 1024 * 1024


async def _save_upload(file: UploadFile) -> tuple[str, str]:
    """Validate an uploaded transaction report and save it to a temporary file."""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_IMPORT_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Upload a CSV, XLS, or XLSX transaction report.",
        )

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="The uploaded transaction report is empty.")
    if len(payload) > MAX_IMPORT_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail="The uploaded transaction report exceeds the 25 MB limit.",
        )

    with NamedTemporaryFile(delete=False, suffix=suffix) as buffer:
        buffer.write(payload)
        return buffer.name, suffix


router = APIRouter(prefix="/transactions", tags=["Transactions"])
SORT_FIELDS = {
    "id": Transaction.id,
    "txn_date": Transaction.txn_date,
    "amount": Transaction.amount,
    "transaction_type": Transaction.transaction_type,
    "status": Transaction.status,
    "customer_id": Transaction.customer_id,
    "ext_txn_id": Transaction.ext_txn_id,
}


@router.get(
    "/{transaction_id}/ai-enrichment",
    response_model=AIEnrichmentRead,
    summary="Get transaction ML enrichment",
    description="Returns the transaction-level anomaly enrichment generated after monitoring.",
    responses={404: {"model": ErrorResponse, "description": "Transaction or enrichment was not found."}},
)
def get_ai_enrichment(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    from backend.app.models.ai_enrichment import TransactionAIEnrichment

    enrichment = (
        db.query(TransactionAIEnrichment)
        .filter(TransactionAIEnrichment.transaction_id == transaction_id)
        .one_or_none()
    )
    if enrichment is None:
        raise HTTPException(status_code=404, detail="AI enrichment not found")
    return enrichment


@router.get(
    "",
    response_model=TransactionListResponse,
    summary="Search and list transactions",
    description="Returns database-filtered, sorted, and paginated transactions. Date filters apply to txn_date.",
    responses={422: {"model": ErrorResponse, "description": "Invalid filters, pagination, or sorting."}},
)
def list_transactions(
    page: int = 1,
    page_size: int = 50,
    search: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    customer_id: str | None = None,
    card_number: str | None = None,
    corporate_name: str | None = None,
    currency: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    amount_min: float | None = None,
    amount_max: float | None = None,
    sort_by: str = "id",
    sort_order: str = "asc",
    db: Session = Depends(get_db),
):
    if page < 1 or page_size < 1 or page_size > 100:
        raise HTTPException(status_code=422, detail="Invalid page or page_size")
    if sort_by not in SORT_FIELDS or sort_order not in {"asc", "desc"}:
        raise HTTPException(status_code=422, detail="Invalid sort field or order")
    if date_from is not None and date_to is not None and date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from must not be after date_to")
    if amount_min is not None and amount_min < 0:
        raise HTTPException(status_code=422, detail="amount_min must not be negative")
    if amount_max is not None and amount_max < 0:
        raise HTTPException(status_code=422, detail="amount_max must not be negative")
    if amount_min is not None and amount_max is not None and amount_min > amount_max:
        raise HTTPException(status_code=422, detail="amount_min must not exceed amount_max")

    query = db.query(Transaction)
    for column, value in (
        (Transaction.transaction_type, transaction_type),
        (Transaction.status, status),
        (Transaction.customer_id, customer_id),
        (Transaction.card_number, card_number),
        (Transaction.corporate_name, corporate_name),
        (Transaction.currency, currency),
    ):
        if value is not None:
            query = query.filter(column == value)
    if date_from is not None:
        query = query.filter(Transaction.txn_date >= date_from)
    if date_to is not None:
        if date_to.time() == datetime.min.time():
            query = query.filter(Transaction.txn_date < date_to + timedelta(days=1))
        else:
            query = query.filter(Transaction.txn_date <= date_to)
    if amount_min is not None:
        query = query.filter(Transaction.amount >= amount_min)
    if amount_max is not None:
        query = query.filter(Transaction.amount <= amount_max)
    if search:
        term = f"%{search.strip()}%"
        query = query.filter(or_(
            Transaction.ext_txn_id.ilike(term),
            cast(Transaction.id, String).ilike(term),
            Transaction.customer_id.ilike(term),
            Transaction.card_number.ilike(term),
            Transaction.rrn.ilike(term),
            Transaction.auth_code.ilike(term),
            Transaction.corporate_name.ilike(term),
        ))

    total = query.count()
    sort_column = SORT_FIELDS[sort_by]
    query = query.order_by((asc if sort_order == "asc" else desc)(sort_column), Transaction.id)
    transactions = query.offset((page - 1) * page_size).limit(page_size).all()
    return TransactionListResponse(
        transactions=transactions,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=ceil(total / page_size) if total else 0,
    )


@router.get(
    "/{transaction_id}",
    response_model=TransactionDetail,
    summary="Get transaction details",
    description="Returns one transaction with its associated alert and case summaries.",
    responses={
        404: {"model": ErrorResponse, "description": "Transaction was not found."},
        422: {"model": ErrorResponse, "description": "The transaction ID is invalid."},
    },
)
def get_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.get(Transaction, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    alerts = db.query(Alert).filter(Alert.transaction_id == transaction.id).order_by(Alert.id).all()
    cases = db.query(Case).join(Alert, Case.alert_id == Alert.id).filter(
        Alert.transaction_id == transaction.id
    ).order_by(Case.id).all()
    return TransactionDetail(
        **TransactionRead.model_validate(transaction).model_dump(),
        alert_count=len(alerts),
        alerts=[
            TransactionAlertSummary(
                id=alert.id, alert_code=alert.alert_code, rule_code=alert.rule_code
            )
            for alert in alerts
        ],
        cases=[
            TransactionCaseSummary(id=case.id, case_code=case.case_code, status=case.status)
            for case in cases
        ],
    )


@router.post(
    "/import",
    summary="Import transaction report",
    description="Imports a pipe-delimited transaction report. The report metadata rows and known CSV fields are handled by the importer.",
    status_code=200,
    responses={
        400: {"model": ErrorResponse, "description": "The uploaded report is malformed or missing required columns."},
        422: {"model": ErrorResponse, "description": "The upload request is invalid."},
    },
)
async def upload_transactions(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    file_path, _ = await _save_upload(file)
    try:
        result = import_transactions(
            file_path,
            db,
            source_filename=file.filename,
            detailed=True,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        Path(file_path).unlink(missing_ok=True)
    return {
        "message": "Transactions imported successfully",
        "import_id": result.import_id,
        "source_filename": result.source_filename,
        "rows_processed": result.rows_processed,
        "records_imported": result.records_imported,
        "duplicates_skipped": result.duplicates_skipped,
        "status": result.status,
    }


@router.post(
    "/import-enhanced",
    summary="Import transaction report with validation",
    description="Imports CSV, XLS, or XLSX transaction reports with flexible column mapping and detailed validation.",
    status_code=200,
    responses={
        400: {"model": ErrorResponse, "description": "The uploaded report is malformed or missing required columns."},
        422: {"model": ErrorResponse, "description": "The upload request is invalid."},
    },
)
async def upload_transactions_enhanced(
    file: UploadFile = File(...),
    skiprows: int = 0,
    db: Session = Depends(get_db),
):
    file_path, _ = await _save_upload(file)
    try:
        result = import_transactions_enhanced(
            file_path,
            db,
            source_filename=file.filename,
            detailed=True,
            skiprows=skiprows,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    finally:
        Path(file_path).unlink(missing_ok=True)

    return TransactionImportResponse(
        message="Transactions imported successfully",
        import_id=result.import_id,
        source_filename=result.source_filename,
        rows_processed=result.rows_processed,
        records_imported=result.records_imported,
        duplicates_skipped=result.duplicates_skipped,
        status=result.status,
        validation=result.validation,
    )
