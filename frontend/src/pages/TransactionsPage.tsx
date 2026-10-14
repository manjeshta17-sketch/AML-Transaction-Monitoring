import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { ApiRequestOptions, TransactionListResponse } from "../types/api";

type Loadable<T> = { data: T | null; loading: boolean; error: string | null };
type SortField = "id" | "txn_date" | "amount" | "transaction_type" | "status" | "customer_id" | "ext_txn_id";
const pageSizeOptions = [25, 50, 100];
const transactionTypes = ["LOAD", "POS", "ATM", "ECOM", "CARD_TO_CARD"];
const statuses = ["PAYMENT_SUCCESS", "REVERSED"];

function paramsToQuery(params: URLSearchParams): ApiRequestOptions["query"] {
  const query: ApiRequestOptions["query"] = {};
  params.forEach((value, key) => { if (value) query[key] = value; });
  return query;
}

function formatDate(value: string | null) {
  return value ? new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)) : "—";
}

function formatAmount(value: number | null, currency: string | null) {
  if (value === null) return "—";
  return `${currency ? `${currency} ` : ""}${new Intl.NumberFormat("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value)}`;
}

function shorten(value: string | null, length = 18) {
  if (!value) return "—";
  return value.length > length ? `${value.slice(0, length - 1)}…` : value;
}

function activeFilterCount(params: URLSearchParams) {
  return [...params.keys()].filter((key) => !["page", "page_size", "sort_by", "sort_order"].includes(key)).length;
}

function StatusBadge({ status }: { status: string | null }) {
  return <span className={`transaction-status ${status === "PAYMENT_SUCCESS" ? "success" : status === "REVERSED" ? "reversed" : ""}`}>{status ?? "Unknown"}</span>;
}

function TransactionTable({ data, sortBy, sortOrder, onSort }: { data: TransactionListResponse; sortBy: SortField; sortOrder: "asc" | "desc"; onSort: (field: SortField) => void }) {
  const sortButton = (label: string, field: SortField) => <button className="sort-button" type="button" onClick={() => onSort(field)}>{label}{sortBy === field && <span aria-label={sortOrder === "asc" ? "ascending" : "descending"}>{sortOrder === "asc" ? " ↑" : " ↓"}</span>}</button>;
  return <div className="table-wrap transaction-table-wrap"><table><caption className="visually-hidden">Transaction results</caption><thead><tr><th>{sortButton("Transaction", "id")}</th><th>{sortButton("Date", "txn_date")}</th><th>Customer</th><th>Card</th><th>Corporate name</th><th>{sortButton("Type", "transaction_type")}</th><th>{sortButton("Amount", "amount")}</th><th>Currency</th><th>{sortButton("Status", "status")}</th><th>Context</th><th>Action</th></tr></thead><tbody>{data.transactions.map((transaction) => <tr key={transaction.id}><td><strong>#{transaction.id}</strong><small>{shorten(transaction.ext_txn_id)}</small></td><td>{formatDate(transaction.txn_date)}</td><td>{shorten(transaction.customer_id)}</td><td>{shorten(transaction.card_number)}</td><td>{shorten(transaction.corporate_name)}</td><td>{transaction.transaction_type ?? "—"}</td><td>{formatAmount(transaction.amount, transaction.currency)}</td><td>{transaction.currency ?? "—"}</td><td><StatusBadge status={transaction.status} /></td><td><span className="neutral-context">Review detail</span></td><td><Link className="text-link" to={`/transactions/${transaction.id}`}>View</Link></td></tr>)}</tbody></table></div>;
}

function TransactionFilters({ params, onApply, onClear }: { params: URLSearchParams; onApply: (event: FormEvent<HTMLFormElement>) => void; onClear: () => void }) {
  return <Card className="transaction-filters"><form onSubmit={onApply}><div className="filter-grid"><div className="filter-field filter-search"><label htmlFor="transaction-search">Search transactions</label><input id="transaction-search" name="search" defaultValue={params.get("search") ?? ""} placeholder="ID, customer, card, RRN, auth code…" /></div><div className="filter-field"><label htmlFor="transaction-type">Transaction type</label><select id="transaction-type" name="transaction_type" defaultValue={params.get("transaction_type") ?? ""}><option value="">All types</option>{transactionTypes.map((type) => <option key={type}>{type}</option>)}</select></div><div className="filter-field"><label htmlFor="transaction-status">Status</label><select id="transaction-status" name="status" defaultValue={params.get("status") ?? ""}><option value="">All statuses</option>{statuses.map((status) => <option key={status}>{status}</option>)}</select></div><div className="filter-field"><label htmlFor="customer-id">Customer ID</label><input id="customer-id" name="customer_id" defaultValue={params.get("customer_id") ?? ""} /></div><div className="filter-field"><label htmlFor="card-number">Card number</label><input id="card-number" name="card_number" defaultValue={params.get("card_number") ?? ""} /></div><div className="filter-field"><label htmlFor="corporate-name">Corporate name</label><input id="corporate-name" name="corporate_name" defaultValue={params.get("corporate_name") ?? ""} /></div><div className="filter-field"><label htmlFor="currency">Currency</label><input id="currency" name="currency" defaultValue={params.get("currency") ?? ""} /></div><div className="filter-field"><label htmlFor="date-from">Date from</label><input id="date-from" name="date_from" type="date" defaultValue={params.get("date_from") ?? ""} /></div><div className="filter-field"><label htmlFor="date-to">Date to</label><input id="date-to" name="date_to" type="date" defaultValue={params.get("date_to") ?? ""} /></div><div className="filter-field"><label htmlFor="amount-min">Minimum amount</label><input id="amount-min" name="amount_min" type="number" min="0" step="0.01" defaultValue={params.get("amount_min") ?? ""} /></div><div className="filter-field"><label htmlFor="amount-max">Maximum amount</label><input id="amount-max" name="amount_max" type="number" min="0" step="0.01" defaultValue={params.get("amount_max") ?? ""} /></div></div><div className="filter-actions"><button className="primary-button" type="submit">Apply filters</button>{activeFilterCount(params) > 0 && <button className="secondary-button" type="button" onClick={onClear}>Clear filters</button>}<span className="filter-hint">Filtering is performed by the backend.</span></div></form></Card>;
}

export function TransactionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [state, setState] = useState<Loadable<TransactionListResponse>>({ data: null, loading: true, error: null });
  const queryKey = searchParams.toString();
  const loadTransactions = useCallback(async () => {
    setState((current) => ({ ...current, loading: true, error: null }));
    try {
      const data = await api.getTransactions(paramsToQuery(searchParams));
      setState({ data, loading: false, error: null });
    } catch (error) {
      setState({ data: null, loading: false, error: error instanceof Error ? error.message : "Unable to load transactions." });
    }
  }, [queryKey]);

  useEffect(() => { void loadTransactions(); }, [loadTransactions]);

  const currentPage = Number(searchParams.get("page") ?? "1");
  const pageSize = Number(searchParams.get("page_size") ?? "25");
  const sortBy = (searchParams.get("sort_by") ?? "id") as SortField;
  const sortOrder = (searchParams.get("sort_order") ?? "desc") as "asc" | "desc";
  const clearFilters = () => setSearchParams({ page: "1", page_size: String(pageSize) });
  const applyFilters = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams({ page: "1", page_size: String(pageSize), sort_by: sortBy, sort_order: sortOrder });
    form.forEach((value, key) => { if (typeof value === "string" && value.trim()) next.set(key, value.trim()); });
    setSearchParams(next);
  };
  const updatePage = (page: number) => { const next = new URLSearchParams(searchParams); next.set("page", String(page)); setSearchParams(next); };
  const updatePageSize = (value: string) => { const next = new URLSearchParams(searchParams); next.set("page_size", value); next.set("page", "1"); setSearchParams(next); };
  const updateSort = (field: SortField) => { const next = new URLSearchParams(searchParams); next.set("sort_by", field); next.set("sort_order", sortBy === field && sortOrder === "asc" ? "desc" : "asc"); next.set("page", "1"); setSearchParams(next); };
  const hasFilters = activeFilterCount(searchParams) > 0;

  return <><PageHeader eyebrow="Investigation workspace" title="Transactions" description="Search and investigate transaction activity across monitored accounts and cards." /><TransactionFilters params={searchParams} onApply={applyFilters} onClear={clearFilters} /><div className="results-toolbar"><div><strong>{state.data ? `${new Intl.NumberFormat("en-US").format(state.data.total)} matching records` : "Transaction results"}</strong>{hasFilters && <span className="toolbar-muted">Filtered view</span>}</div><label htmlFor="transaction-page-size">Rows <select id="transaction-page-size" value={String(pageSize)} onChange={(event) => updatePageSize(event.target.value)}>{pageSizeOptions.map((size) => <option key={size}>{size}</option>)}</select></label></div>{state.loading ? <Card><LoadingState /></Card> : state.error ? <Card><ErrorState message={state.error} /><button className="secondary-button retry-button" type="button" onClick={() => void loadTransactions()}>Retry</button></Card> : state.data?.transactions.length ? <Card><TransactionTable data={state.data} sortBy={sortBy} sortOrder={sortOrder} onSort={updateSort} /><div className="pagination"><span>Page {state.data.page} of {state.data.total_pages || 1}</span><div><button className="secondary-button" type="button" disabled={currentPage <= 1} onClick={() => updatePage(currentPage - 1)}>Previous</button><button className="secondary-button" type="button" disabled={currentPage >= state.data.total_pages} onClick={() => updatePage(currentPage + 1)}>Next</button></div></div></Card> : <Card><EmptyState title={hasFilters ? "No transactions match your filters" : "No transactions available"} description={hasFilters ? "Try adjusting or clearing the current search and filters." : "No transaction records are currently available from the backend."} />{hasFilters && <button className="secondary-button empty-action" type="button" onClick={clearFilters}>Clear filters</button>}</Card>}</>;
}
