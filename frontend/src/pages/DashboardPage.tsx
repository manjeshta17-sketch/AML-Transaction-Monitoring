import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type {
  AlertListResponse,
  DashboardDistribution,
  DashboardSummary,
  RuleAlertCount,
  TrendPoint,
} from "../types/api";

type Loadable<T> = { data: T | null; loading: boolean; error: string | null };
type Range = "24h" | "7d" | "30d";

const initialState = <T,>(): Loadable<T> => ({ data: null, loading: true, error: null });

function useDashboardData(range: Range) {
  const [summary, setSummary] = useState<Loadable<DashboardSummary>>(initialState());
  const [transactions, setTransactions] = useState<Loadable<TrendPoint[]>>(initialState());
  const [alerts, setAlerts] = useState<Loadable<TrendPoint[]>>(initialState());
  const [rules, setRules] = useState<Loadable<RuleAlertCount[]>>(initialState());
  const [distributions, setDistributions] = useState<Loadable<DashboardDistribution>>(initialState());
  const [recentAlerts, setRecentAlerts] = useState<Loadable<AlertListResponse>>(initialState());

  useEffect(() => {
    let cancelled = false;
    const load = async <T,>(request: Promise<T>, update: (state: Loadable<T>) => void) => {
      update({ data: null, loading: true, error: null });
      try {
        const data = await request;
        if (!cancelled) update({ data, loading: false, error: null });
      } catch (error) {
        if (!cancelled) {
          update({
            data: null,
            loading: false,
            error: error instanceof Error ? error.message : "Unable to load this section.",
          });
        }
      }
    };

    void load(api.getDashboardSummary({ time_range: range }), setSummary);
    void load(api.getTransactionTrend(range), setTransactions);
    void load(api.getAlertTrend(range), setAlerts);
    void load(api.getTopRules(), setRules);
    void load(api.getDistributions(), setDistributions);
    void load(api.getAlerts({ page: 1, page_size: 8, sort_by: "created_at", sort_order: "desc" }), setRecentAlerts);
    return () => {
      cancelled = true;
    };
  }, [range]);

  return { summary, transactions, alerts, rules, distributions, recentAlerts };
}

function formatNumber(value: number) {
  return new Intl.NumberFormat("en-US").format(value);
}

function formatAmount(value: number) {
  return new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 }).format(value);
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(new Date(value));
}

function SectionState<T>({ state, children, empty }: { state: Loadable<T>; children: (data: T) => ReactNode; empty: string }) {
  if (state.loading) return <LoadingState />;
  if (state.error) return <ErrorState message={state.error} />;
  if (!state.data || (Array.isArray(state.data) && state.data.length === 0)) return <EmptyState title="No data available" description={empty} />;
  return <>{children(state.data)}</>;
}

function TrendChart({ points, tone }: { points: TrendPoint[]; tone: "blue" | "amber" }) {
  const max = Math.max(...points.map((point) => point.count), 1);
  const width = 680;
  const height = 170;
  const line = points.map((point, index) => {
    const x = points.length === 1 ? width / 2 : (index / (points.length - 1)) * width;
    const y = height - (point.count / max) * (height - 24) - 8;
    return `${x},${y}`;
  }).join(" ");
  return (
    <div className="trend-visual">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Trend with ${points.length} time periods`}>
        <line x1="0" y1={height - 8} x2={width} y2={height - 8} className="chart-axis" />
        <polyline points={line} className={`chart-line ${tone}`} fill="none" />
        {points.map((point, index) => {
          const [x, y] = line.split(" ")[index].split(",");
          return <circle key={point.bucket} cx={x} cy={y} r="3.5" className={`chart-point ${tone}`} />;
        })}
      </svg>
      <div className="trend-footer"><span>{points[0] ? formatDate(points[0].bucket) : ""}</span><strong>{formatNumber(points.reduce((sum, point) => sum + point.count, 0))} total</strong><span>{points.at(-1) ? formatDate(points.at(-1)!.bucket) : ""}</span></div>
    </div>
  );
}

function DistributionBars({ values, label }: { values: Record<string, number>; label: string }) {
  const entries = Object.entries(values);
  const max = Math.max(...entries.map(([, value]) => value), 1);
  if (!entries.length) return <EmptyState title={`No ${label.toLowerCase()} data`} description="The API returned no distribution values for this dataset." />;
  return <div className="distribution-list" aria-label={label}>{entries.map(([key, value]) => <div className="distribution-row" key={key}><span>{key}</span><div className="distribution-track"><span style={{ width: `${(value / max) * 100}%` }} /></div><strong>{formatNumber(value)}</strong></div>)}</div>;
}

function Kpi({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return <Card className="kpi-card"><span className="kpi-label">{label}</span><strong className="kpi-value">{value}</strong>{detail && <span className="kpi-detail">{detail}</span>}</Card>;
}

export function DashboardPage() {
  const [range, setRange] = useState<Range>("30d");
  const { summary, transactions, alerts, rules, distributions, recentAlerts } = useDashboardData(range);
  const caseWorkload = useMemo(() => {
    const cases = summary.data?.cases.by_status ?? {};
    return (cases.OPEN ?? 0) + (cases.IN_PROGRESS ?? 0);
  }, [summary.data]);

  return (
    <>
      <PageHeader eyebrow="Operations overview" title="Transaction Monitoring" description="Operational view of transaction activity, alerts, cases, and AML rule activity." />
      <div className="dashboard-controls">
        <label htmlFor="dashboard-range">Summary and trend range</label>
        <select id="dashboard-range" value={range} onChange={(event) => setRange(event.target.value as Range)}>
          <option value="24h">Last 24 hours</option><option value="7d">Last 7 days</option><option value="30d">Last 30 days</option>
        </select>
      </div>
      {summary.loading ? <LoadingState /> : summary.error ? <ErrorState message={summary.error} /> : summary.data ? <section className="kpi-grid" aria-label="Monitoring summary">
        <Kpi label="Total transactions" value={formatNumber(summary.data.transactions.total_transactions)} />
        <Kpi label="Transaction amount" value={formatAmount(summary.data.transactions.total_transaction_amount)} detail="All currencies as reported" />
        <Kpi label="Total alerts" value={formatNumber(summary.data.alerts.total_alerts)} detail={`${formatNumber(summary.data.alerts.open_alerts)} open`} />
        <Kpi label="Open alerts" value={formatNumber(summary.data.alerts.open_alerts)} />
        <Kpi label="Case workload" value={formatNumber(caseWorkload)} detail={`${formatNumber(summary.data.cases.total_cases)} total cases`} />
        <Kpi label="High priority alerts" value={formatNumber(summary.data.high_priority_alerts)} detail="Priority 1" />
      </section> : null}

      <section className="dashboard-grid trend-grid">
        <Card><div className="section-heading"><div><h2>Transaction activity</h2><p>Transactions grouped across the selected range.</p></div><span className="legend blue">Transactions</span></div><SectionState state={transactions} empty="No transactions were returned for the selected range.">{(data) => <TrendChart points={data} tone="blue" />}</SectionState></Card>
        <Card><div className="section-heading"><div><h2>Alert activity</h2><p>Alerts grouped across the selected range.</p></div><span className="legend amber">Alerts</span></div><SectionState state={alerts} empty="No alerts were returned for the selected range.">{(data) => <TrendChart points={data} tone="amber" />}</SectionState></Card>
      </section>

      <section className="dashboard-grid lower-grid">
        <Card><div className="section-heading"><div><h2>Top triggered rules</h2><p>All-time alert volume, ordered by the API.</p></div></div><SectionState state={rules} empty="No rule activity was returned.">{(data) => <div className="rule-list">{data.map((rule) => <div className="rule-row" key={rule.rule_code}><div><strong>{rule.rule_code}</strong><span>{rule.rule_name}</span></div><b>{formatNumber(rule.alert_count)}</b></div>)}</div>}</SectionState></Card>
        <Card><div className="section-heading"><div><h2>Transaction types</h2><p>Distribution from the selected summary range.</p></div></div><SectionState state={summary} empty="No transaction-type distribution was returned.">{(data) => <DistributionBars values={data.transactions.transaction_types} label="Transaction types" />}</SectionState></Card>
        <Card><div className="section-heading"><div><h2>Alert and case profile</h2><p>Current distribution returned by the dashboard API.</p></div></div><SectionState state={distributions} empty="No alert or case distribution was returned.">{(data) => <div className="profile-grid"><div><h3>Alert risk</h3><DistributionBars values={data.alerts_by_risk_level} label="Alert risk" /></div><div><h3>Alert priority</h3><DistributionBars values={data.alerts_by_priority} label="Alert priority" /></div><div><h3>Case priority</h3><DistributionBars values={data.cases_by_priority} label="Case priority" /></div></div>}</SectionState></Card>
      </section>

      <Card className="recent-alerts"><div className="section-heading"><div><h2>Recent alerts</h2><p>Latest alerts ordered by creation time.</p></div><Link className="text-link" to="/alerts">View alerts</Link></div><SectionState state={recentAlerts} empty="No alerts were returned by the operational queue.">{(data) => <div className="table-wrap"><table><caption className="visually-hidden">Recent alerts</caption><thead><tr><th>Alert</th><th>Rule</th><th>Priority</th><th>Status</th><th>Created</th><th>Assignment</th></tr></thead><tbody>{data.alerts.map((alert) => <tr key={alert.id}><td><strong>{alert.alert_code}</strong></td><td>{alert.rule_code}</td><td><span className={`priority priority-${alert.priority}`}>P{alert.priority}</span></td><td><span className="status-badge">{alert.status}</span></td><td>{formatDate(alert.created_at)}</td><td>{alert.assigned_to ?? "Unassigned"}</td></tr>)}</tbody></table></div>}</SectionState></Card>
    </>
  );
}
