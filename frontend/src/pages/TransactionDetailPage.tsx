import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { TransactionDetail } from "../types/api";

function value(value: string | number | null) { return value === null || value === "" ? "—" : String(value); }
function date(valueToFormat: string | null) { return valueToFormat ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(valueToFormat)) : "—"; }
function money(amount: number | null, currency: string | null) { return amount === null ? "—" : `${currency ? `${currency} ` : ""}${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2 }).format(amount)}`; }

function DetailGrid({ fields }: { fields: Array<[string, string]> }) {
  return <dl className="detail-grid">{fields.map(([label, fieldValue]) => <div key={label}><dt>{label}</dt><dd>{fieldValue}</dd></div>)}</dl>;
}

export function TransactionDetailPage() {
  const { transactionId } = useParams();
  const [state, setState] = useState<{ data: TransactionDetail | null; loading: boolean; error: string | null }>({ data: null, loading: true, error: null });
  useEffect(() => {
    if (!transactionId) return;
    let active = true;
    void api.getTransaction(transactionId).then((data) => { if (active) setState({ data, loading: false, error: null }); }).catch((error: unknown) => { if (active) setState({ data: null, loading: false, error: error instanceof Error ? error.message : "Unable to load this transaction." }); });
    return () => { active = false; };
  }, [transactionId]);

  if (state.loading) return <><PageHeader eyebrow="Transaction investigation" title="Transaction detail" description="Review transaction attributes and monitoring context." /><Card><LoadingState /></Card></>;
  if (state.error || !state.data) return <><PageHeader eyebrow="Transaction investigation" title="Transaction detail" description="Review transaction attributes and monitoring context." /><Card><ErrorState message={state.error ?? "Transaction not found."} /><Link className="secondary-button inline-button" to="/transactions">Back to transactions</Link></Card></>;
  const transaction = state.data;
  return <><div className="detail-back"><Link to="/transactions">← Back to transactions</Link></div><PageHeader eyebrow="Transaction investigation" title={`Transaction #${transaction.id}`} description="Review transaction attributes and monitoring context." /><div className="detail-layout"><div className="detail-main"><Card><div className="section-heading"><div><h2>Transaction details</h2><p>Core transaction and account information.</p></div><span className="transaction-status detail-status">{value(transaction.status)}</span></div><DetailGrid fields={[["Transaction ID", value(transaction.id)], ["External transaction ID", value(transaction.ext_txn_id)], ["Transaction date", date(transaction.txn_date)], ["Amount", money(transaction.amount, transaction.currency)], ["Transaction type", value(transaction.transaction_type)], ["Status", value(transaction.status)], ["Currency", value(transaction.currency)], ["Customer ID", value(transaction.customer_id)], ["Card number", value(transaction.card_number)], ["Corporate name", value(transaction.corporate_name)]]} /></Card><Card><div className="section-heading"><div><h2>Additional details</h2><p>Fields supplied by the transaction detail API.</p></div></div><DetailGrid fields={[["RRN", value(transaction.rrn)], ["Auth code", value(transaction.auth_code)], ["Product", value(transaction.product)], ["MCC", value(transaction.mcc)], ["Fees", money(transaction.fees, transaction.currency)], ["CR/DR flag", value(transaction.cr_dr_flag)], ["Other party ID", value(transaction.other_party_id)], ["Other party name", value(transaction.other_party_name)], ["Wallet balance", money(transaction.post_wallet_balance, transaction.currency)], ["Description", value(transaction.description)]]} /></Card></div><aside className="detail-sidebar"><Card><div className="section-heading"><div><h2>Monitoring context</h2><p>Related alert and case summaries.</p></div></div><div className="context-summary"><strong>{transaction.alert_count} alert{transaction.alert_count === 1 ? "" : "s"}</strong>{transaction.alerts.length ? transaction.alerts.map((alert) => <div className="context-item" key={alert.id}><strong>{alert.alert_code}</strong><span>{alert.rule_code}</span></div>) : <p>No alert</p>}</div>{transaction.cases.length ? <div className="context-summary case-context"><strong>{transaction.cases.length} case{transaction.cases.length === 1 ? "" : "s"}</strong>{transaction.cases.map((caseItem) => <div className="context-item" key={caseItem.id}><strong>{caseItem.case_code}</strong><span>{caseItem.status}</span></div>)}</div> : <div className="context-summary case-context"><strong>No case</strong><p>No case is associated with this transaction.</p></div>}<div className="context-links"><Link to="/alerts">Open alerts workspace</Link><Link to="/cases">Open cases workspace</Link></div></Card></aside></div></>;
}
