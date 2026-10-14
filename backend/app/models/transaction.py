from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String
from backend.app.core.database import Base
from backend.app.models.transaction_import import TransactionImport as _TransactionImport


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    import_id = Column(Integer, ForeignKey("transaction_imports.id"), nullable=True, index=True)

    txn_date = Column(DateTime, nullable=True, index=True)
    corporate_name = Column(String, nullable=True, index=True)

    proxy_card_number = Column(String, nullable=True)
    card_number = Column(String, nullable=True)

    rrn = Column(String, nullable=True, index=True)
    auth_code = Column(String, nullable=True, index=True)
    ext_txn_id = Column(String, nullable=True, index=True)

    amount = Column(Float, nullable=True)

    transaction_type = Column(String, nullable=True, index=True)
    status = Column(String, nullable=True, index=True)

    customer_id = Column(String, nullable=True, index=True)

    post_wallet_balance = Column(Float, nullable=True)

    cr_dr_flag = Column(String, nullable=True)

    other_party_id = Column(String, nullable=True)
    other_party_name = Column(String, nullable=True)

    currency = Column(String, nullable=True, index=True)
    home_currency = Column(String, nullable=True)
    country_code = Column(String, nullable=True)
    domestic_status = Column(String, nullable=True)
    load_source = Column(String, nullable=True)
    settlement_currency = Column(String, nullable=True)
    originating_country_currency = Column(String, nullable=True)
    product = Column(String, nullable=True)

    txn_amount = Column(Float, nullable=True)
    fees = Column(Float, nullable=True)

    description = Column(String, nullable=True)

    mcc = Column(String, nullable=True)

    activation_date = Column(DateTime, nullable=True)