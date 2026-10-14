import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Card } from "../components/Card";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { RuleConfiguration } from "../types/api";

function formatDate(value: string) {
  return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

export function RulesPage() {
  const [rules, setRules] = useState<RuleConfiguration[] | null>(null);
  const [search, setSearch] = useState("");
  const [enabled, setEnabled] = useState("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try { setRules(await api.getRules()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load rule configurations."); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(); }, [load]);
  const visibleRules = useMemo(() => {
    if (!rules) return [];
    const term = search.trim().toLowerCase();
    return rules.filter((rule) => {
      const matchesSearch = !term || [rule.rule_code, rule.name, rule.category, rule.description].some((value) => value.toLowerCase().includes(term));
      const matchesEnabled = !enabled || String(rule.enabled) === enabled;
      return matchesSearch && matchesEnabled;
    });
  }, [rules, search, enabled]);
  return <>
    <PageHeader eyebrow="Configuration workspace" title="AML Rules" description="Manage transaction-monitoring rules, thresholds and activation status." />
    {rules && <Card className="rule-filters"><div className="filter-grid"><div className="filter-field filter-search"><label htmlFor="rule-search">Search rules</label><input id="rule-search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Code, name, category…" /></div><div className="filter-field"><label htmlFor="rule-enabled">Enabled</label><select id="rule-enabled" value={enabled} onChange={(event) => setEnabled(event.target.value)}><option value="">All rules</option><option value="true">Enabled</option><option value="false">Disabled</option></select></div></div></Card>}
    {loading ? <Card><LoadingState /></Card> : error ? <Card><ErrorState message={error} /><button className="secondary-button retry-button" type="button" onClick={() => void load()}>Retry</button></Card> : !rules?.length ? <Card><EmptyState title="No rule configurations available" description="The backend returned an empty rule catalogue." /></Card> : !visibleRules.length ? <Card><EmptyState title="No rules match your search" description="Try a different search term or enabled filter." /></Card> : <Card><div className="results-toolbar"><strong>{visibleRules.length} of {rules.length} rules</strong></div><div className="table-wrap transaction-table-wrap"><table><caption className="visually-hidden">AML rule configurations</caption><thead><tr><th>Rule code</th><th>Rule name</th><th>Category</th><th>Risk</th><th>Priority</th><th>Enabled</th><th>Description</th><th>Updated</th><th>Action</th></tr></thead><tbody>{visibleRules.map((rule) => <tr key={rule.rule_code}><td><strong>{rule.rule_code}</strong></td><td>{rule.name}</td><td>{rule.category}</td><td><span className={`risk-label risk-${rule.risk_level.toLowerCase()}`}>{rule.risk_level}</span></td><td><span className={`priority priority-${rule.priority}`}>P{rule.priority}</span></td><td><span className={`enabled-status ${rule.enabled ? "enabled" : "disabled"}`}>{rule.enabled ? "Enabled" : "Disabled"}</span></td><td className="rule-description">{rule.description}</td><td>{formatDate(rule.updated_at)}</td><td><Link className="text-link" to={`/rules/${encodeURIComponent(rule.rule_code)}`}>View / edit</Link></td></tr>)}</tbody></table></div></Card>}
  </>;
}
