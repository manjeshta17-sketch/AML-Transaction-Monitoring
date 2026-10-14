import { FormEvent, useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { RuleConfiguration } from "../types/api";

function formatDate(value: string) { return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function inputValue(value: unknown) { return Array.isArray(value) ? value.join(", ") : String(value ?? ""); }
function parseValue(original: unknown, value: string): unknown {
  if (Array.isArray(original)) return value.split(",").map((item) => item.trim()).filter(Boolean);
  if (typeof original === "number") return Number(value);
  return value;
}

export function RuleDetailPage() {
  const { ruleCode } = useParams();
  const [rule, setRule] = useState<RuleConfiguration | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);
  const load = useCallback(async () => {
    if (!ruleCode) return;
    setLoading(true); setError(null);
    try { setRule(await api.getRule(ruleCode)); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load this rule."); }
    finally { setLoading(false); }
  }, [ruleCode]);
  useEffect(() => { void load(); }, [load]);
  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!rule) return;
    const data = new FormData(event.currentTarget);
    const parameters = Object.fromEntries(Object.entries(rule.parameters).map(([key, original]) => [key, parseValue(original, String(data.get(`parameter_${key}`) ?? ""))]));
    setSaving(true); setFeedback(null);
    try {
      const updated = await api.updateRule(rule.rule_code, { enabled: data.get("enabled") === "true", priority: Number(data.get("priority")), risk_level: String(data.get("risk_level")), parameters });
      setRule(updated); setFeedback("Rule configuration saved. The change applies to future monitoring runs.");
    } catch (reason) { setFeedback(reason instanceof Error ? reason.message : "The rule configuration could not be saved."); }
    finally { setSaving(false); }
  };
  if (loading) return <><PageHeader eyebrow="Configuration workspace" title="Rule detail" description="Review and update a persisted AML rule configuration." /><Card><LoadingState /></Card></>;
  if (error || !rule) return <><PageHeader eyebrow="Configuration workspace" title="Rule detail" description="Review and update a persisted AML rule configuration." /><Card><ErrorState message={error ?? "Rule not found."} /><Link className="secondary-button inline-button" to="/rules">Back to rules</Link></Card></>;
  return <><div className="detail-back"><Link to="/rules">← Back to rules</Link></div><PageHeader eyebrow="Configuration workspace" title={rule.rule_code} description={rule.name} />{feedback && <div className="inline-feedback" role="status">{feedback}</div>}<form onSubmit={save}><div className="detail-layout"><div className="detail-main"><Card><div className="section-heading"><div><h2>Rule configuration</h2><p>Backend validation remains authoritative for all changes.</p></div><span className={`enabled-status ${rule.enabled ? "enabled" : "disabled"}`}>{rule.enabled ? "Enabled" : "Disabled"}</span></div><dl className="detail-grid"><div><dt>Rule code</dt><dd>{rule.rule_code}</dd></div><div><dt>Name</dt><dd>{rule.name}</dd></div><div><dt>Category</dt><dd>{rule.category}</dd></div><div><dt>Description</dt><dd>{rule.description}</dd></div><div><dt>Created</dt><dd>{formatDate(rule.created_at)}</dd></div><div><dt>Updated</dt><dd>{formatDate(rule.updated_at)}</dd></div></dl></Card><Card><div className="section-heading"><div><h2>Rule parameters</h2><p>Only parameters returned by this rule are editable.</p></div></div><div className="parameter-grid">{Object.entries(rule.parameters).map(([key, value]) => <label key={key} htmlFor={`parameter_${key}`}><span>{key.replaceAll("_", " ")}</span><input id={`parameter_${key}`} name={`parameter_${key}`} defaultValue={inputValue(value)} disabled={saving} /><small>{Array.isArray(value) ? "Comma-separated list" : typeof value}</small></label>)}</div></Card></div><aside className="detail-sidebar"><Card><div className="section-heading"><div><h2>Change settings</h2><p>Changes affect future monitoring runs.</p></div></div><div className="action-stack"><label htmlFor="rule-enabled-action">Activation<select id="rule-enabled-action" name="enabled" defaultValue={String(rule.enabled)} disabled={saving}><option value="true">Enabled</option><option value="false">Disabled</option></select></label><label htmlFor="rule-risk-action">Risk level<select id="rule-risk-action" name="risk_level" defaultValue={rule.risk_level} disabled={saving}>{["low", "medium", "high", "critical"].map((value) => <option key={value}>{value}</option>)}</select></label><label htmlFor="rule-priority-action">Priority<input id="rule-priority-action" name="priority" type="number" min="1" step="1" defaultValue={rule.priority} disabled={saving} /></label><button className="primary-button" type="submit" disabled={saving}>{saving ? "Saving…" : "Save configuration"}</button></div></Card></aside></div></form></>;
}
