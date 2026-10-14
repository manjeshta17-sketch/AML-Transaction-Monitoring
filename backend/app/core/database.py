from sqlalchemy import create_engine
from sqlalchemy import inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = "sqlite:///./aml.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

Base = declarative_base()


def ensure_transaction_rule_columns() -> None:
    """Add nullable explicit international-rule fields to existing SQLite databases."""
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("transactions")
    }
    with engine.begin() as connection:
        for column in (
            "home_currency",
            "country_code",
            "domestic_status",
            "load_source",
            "settlement_currency",
            "originating_country_currency",
        ):
            if column not in existing_columns:
                connection.execute(text(f"ALTER TABLE transactions ADD COLUMN {column} VARCHAR"))


def ensure_transaction_import_columns() -> None:
    """Add nullable import provenance to existing transaction databases."""
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("transactions")
    }
    with engine.begin() as connection:
        if "import_id" not in existing_columns:
            connection.execute(text("ALTER TABLE transactions ADD COLUMN import_id INTEGER"))
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_transactions_import_id "
                "ON transactions (import_id)"
            )
        )


def ensure_alert_columns() -> None:
    """Add alert workflow metadata to existing SQLite databases."""
    existing_columns = {
        column["name"] for column in inspect(engine).get_columns("alerts")
    }
    with engine.begin() as connection:
        if "description" not in existing_columns:
            connection.execute(text("ALTER TABLE alerts ADD COLUMN description VARCHAR"))
            connection.execute(text("UPDATE alerts SET description = rule_name WHERE description IS NULL"))
        if "assigned_to" not in existing_columns:
            connection.execute(text("ALTER TABLE alerts ADD COLUMN assigned_to VARCHAR"))
        if "updated_at" not in existing_columns:
            connection.execute(text("ALTER TABLE alerts ADD COLUMN updated_at DATETIME"))
            connection.execute(text("UPDATE alerts SET updated_at = created_at WHERE updated_at IS NULL"))


def ensure_transaction_search_indexes() -> None:
    """Add indexes used by transaction search to existing SQLite databases."""
    statements = (
        "CREATE INDEX IF NOT EXISTS ix_transactions_txn_date ON transactions (txn_date)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_corporate_name ON transactions (corporate_name)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_rrn ON transactions (rrn)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_auth_code ON transactions (auth_code)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_ext_txn_id ON transactions (ext_txn_id)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_transaction_type ON transactions (transaction_type)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_status ON transactions (status)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_customer_id ON transactions (customer_id)",
        "CREATE INDEX IF NOT EXISTS ix_transactions_currency ON transactions (currency)",
    )
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))