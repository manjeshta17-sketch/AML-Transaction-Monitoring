import { FormEvent, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { AIEnrichment, AlertDetail, LLMAssistance } from "../types/api";

function date(value: string) { return new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value)); }
function money(value: number | null) { return value === null ? "—" : new Intl.NumberFormat("en-US", { minimumFractionDigits: 2 }).format(value); }
function text(value: string | number | null) { return value === null || value === "" ? "—" : String(value); }
function Grid({ fields }: { fields: Array<[string, string]> }) { return <dl className="detail-grid">{fields.map(([label, item]) => <div key={label}><dt>{label}</dt><dd>{item}</dd></div>)}</dl>; }
function assistanceSections(response: string | null) {
  if (!response) return null;
  const headers = ["Alert Summary", "Evidence", "Missing Information", "Recommended Analyst Checks"];
  return headers.map((header, index) => {
    const start = response.indexOf(`## ${header}`) + header.length + 3;
    const end = index < headers.length - 1 ? response.indexOf(`## ${headers[index + 1]}`) : response.length;
    return { header, content: response.slice(start, end < 0 ? response.length : end).trim() };
  });
}

export function AlertDetailPage() {
  const { alertId } = useParams();
  const [alert, setAlert] = useState<AlertDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mutation, setMutation] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [mlState, setMlState] = useState<{ data: AIEnrichment | null; loading: boolean; error: string | null }>({ data: null, loading: true, error: null });
  const [assistance, setAssistance] = useState<LLMAssistance | null>(null);
  const [assistanceState, setAssistanceState] = useState<"idle" | "generating" | "available" | "unavailable" | "invalid" | "error">("idle");
  const [assistanceError, setAssistanceError] = useState<string | null>(null);
  const load = async () => { if (!alertId) return; setLoading(true); setError(null); try { setAlert(await api.getAlert(alertId)); } catch (reason) { setError(reason instanceof Error ? reason.message : "Unable to load alert."); } finally { setLoading(false); } };
  useEffect(() => { void load(); }, [alertId]);
  useEffect(() => {
    if (!alert?.transaction_id) return;
    setMlState({ data: null, loading: true, error: null });
    void api.getAIEnrichment(alert.transaction_id)
      .then((data) => setMlState({ data, loading: false, error: null }))
      .catch((reason: unknown) => setMlState({ data: null, loading: false, error: reason instanceof Error ? reason.message : "Unable to load behavioral enrichment." }));
  }, [alert?.transaction_id]);
  const mutate = async (operation: string, request: Promise<unknown>, success: string) => { setMutation(operation); setMessage(null); try { await request; await load(); setMessage(success); } catch (reason) { setMessage(reason instanceof Error ? reason.message : "The alert update could not be completed."); } finally { setMutation(null); } };
  const statusChange = (event: FormEvent<HTMLSelectElement>) => { if (alert) void mutate("status", api.updateAlertStatus(alert.id, event.currentTarget.value), "Status updated."); };
  const priorityChange = (event: FormEvent<HTMLSelectElement>) => { if (alert) void mutate("priority", api.updateAlertPriority(alert.id, Number(event.currentTarget.value)), "Priority updated."); };
  const assignment = (event: FormEvent<HTMLFormElement>) => { event.preventDefault(); if (alert) { const value = new FormData(event.currentTarget).get("assigned_to"); void mutate("assignment", api.updateAlertAssignment(alert.id, typeof value === "string" && value.trim() ? value.trim() : null), "Assignment updated."); } };
  const createCase = () => { if (alert) void mutate("case", api.createCaseFromAlert(alert.id), "Case created."); };
  const generateAssistance = async () => {
    if (!alert) return;
    setAssistanceState("generating");
    setAssistance(null);
    setAssistanceError(null);
    try {
      const result = await api.generateAIAssistance(alert.id);
      setAssistance(result);
      setAssistanceState(result.response_status === "VALID" && result.validated ? "available" : result.response_status === "INVALID" ? "invalid" : result.response_status === "ERROR" || result.response_status === "TIMEOUT" ? "error" : "unavailable");
    } catch (reason) {
      setAssistanceState("error");
      setAssistanceError(reason instanceof Error ? reason.message : "Unable to generate AI assistance.");
    }
  };
  const sections = assistanceSections(assistance?.generated_response ?? null);
  if (loading) return <><PageHeader eyebrow="Alert investigation" title="Alert detail" description="Review an alert and its transaction context." /><Card><LoadingState /></Card></>;
  if (error || !alert) return <><PageHeader eyebrow="Alert investigation" title="Alert detail" description="Review an alert and its transaction context." /><Card><ErrorState message={error ?? "Alert not found."} /><Link className="secondary-button inline-button" to="/alerts">Back to alerts</Link></Card></>;
  return <><div className="detail-back"><Link to="/alerts">← Back to alerts</Link></div><PageHeader eyebrow="Alert investigation" title={alert.alert_code} description="Review the AML rule signal, workflow status and source transaction." />{message && <div className={`inline-feedback ${message.endsWith(".") && !message.includes("could") ? "success-feedback" : "error-feedback"}`} role="status">{message}</div>}<div className="detail-layout"><div className="detail-main"><Card><div className="section-heading"><div><h2>Alert information</h2><p>Signal and workflow attributes.</p></div><span className={`alert-status ${alert.status.toLowerCase()}`}>{alert.status}</span></div><Grid fields={[["Alert code", alert.alert_code], ["Alert ID", text(alert.id)], ["Rule code", alert.rule_code], ["Rule name", alert.rule_name], ["Description", text(alert.description)], ["Risk level", alert.risk_level], ["Priority", `P${alert.priority}`], ["Assigned to", alert.assigned_to ?? "Unassigned"], ["Created", date(alert.created_at)], ["Updated", date(alert.updated_at)]]} /></Card><Card><div className="section-heading"><div><h2>Transaction context</h2><p>Bounded source transaction summary returned by the alert API.</p></div></div>{alert.transaction ? <><Grid fields={[["Transaction ID", text(alert.transaction.id)], ["External transaction ID", text(alert.transaction.ext_txn_id)], ["Transaction date", alert.transaction.txn_date ? date(alert.transaction.txn_date) : "—"], ["Transaction type", text(alert.transaction.transaction_type)], ["Amount", money(alert.transaction.amount)], ["Customer ID", text(alert.transaction.customer_id)], ["Card number", text(alert.transaction.card_number)]]} /><Link className="secondary-button inline-button" to={`/transactions/${alert.transaction.id}`}>Open transaction</Link></> : <p className="detail-note">No source transaction summary is available.</p>}</Card><Card><div className="section-heading"><div><h2>Behavioral Anomaly Enrichment</h2><p>Model-generated context only; this is not a fraud determination.</p></div></div>{mlState.loading ? <LoadingState /> : mlState.error ? <p className="detail-note">Behavioral enrichment unavailable: {mlState.error}</p> : mlState.data ? <Grid fields={[["Model version", mlState.data.model_version], ["Feature pipeline version", mlState.data.feature_pipeline_version], ["Anomaly score", mlState.data.anomaly_score === null ? "—" : String(mlState.data.anomaly_score)], ["Anomaly flag", mlState.data.anomaly_flag === null ? "Not scored" : mlState.data.anomaly_flag ? "Detected" : "Not detected"], ["History sufficiency", mlState.data.history_sufficient ? "Sufficient" : "Insufficient history"], ["Enrichment status", mlState.data.enrichment_status === "INSUFFICIENT_HISTORY" ? "Insufficient History" : mlState.data.enrichment_status]]} /> : <p className="detail-note">No behavioral enrichment is available.</p>}</Card><Card><div className="section-heading"><div><h2>AI Analyst Assistance</h2><p>AI-generated analyst assistance</p></div></div><p className="ai-disclaimer">AI assistance is based on available transaction, rule, and behavioral evidence. It does not make the final AML/fraud decision.</p><button className="primary-button" type="button" onClick={generateAssistance} disabled={assistanceState === "generating"}>{assistanceState === "generating" ? "Generating…" : "Generate AI Assistance"}</button>{assistanceState === "generating" && <div className="ai-state"><LoadingState /></div>}{assistanceState === "unavailable" && <p className="ai-state ai-state-warning">AI assistance is unavailable: {assistance?.response_status ?? "provider unavailable"}. No generated answer was returned.</p>}{assistanceState === "invalid" && <p className="ai-state ai-state-warning">The provider response did not pass safety validation and is not shown as trusted assistance.</p>}{assistanceState === "error" && <p className="ai-state ai-state-warning">{assistanceError ?? "AI assistance could not be generated."}</p>}{assistanceState === "available" && sections && <div className="ai-response">{sections.map((section) => <section key={section.header}><h3>{section.header}</h3><p>{section.content}</p></section>)}</div>}</Card></div><aside className="detail-sidebar"><Card><div className="section-heading"><div><h2>Analyst actions</h2><p>Changes are saved through the alert API.</p></div></div><div className="action-stack"><label htmlFor="alert-status-action">Status<select id="alert-status-action" value={alert.status} disabled={mutation !== null} onChange={statusChange}><option>OPEN</option><option>IN_PROGRESS</option><option>CLOSED</option></select></label><label htmlFor="alert-priority-action">Priority<select id="alert-priority-action" value={String(alert.priority)} disabled={mutation !== null} onChange={priorityChange}>{[1, 2, 3, 4].map((item) => <option key={item}>{item}</option>)}</select></label><form onSubmit={assignment}><label htmlFor="alert-assignment">Assignment<input id="alert-assignment" name="assigned_to" defaultValue={alert.assigned_to ?? ""} placeholder="Analyst identifier" disabled={mutation !== null} /></label><button className="secondary-button" type="submit" disabled={mutation !== null}>{mutation === "assignment" ? "Saving…" : "Save assignment"}</button></form><button className="primary-button" type="button" onClick={createCase} disabled={mutation !== null}>{mutation === "case" ? "Creating…" : "Create case"}</button>{mutation && mutation !== "assignment" && <span className="filter-hint">Saving {mutation}…</span>}</div></Card><Card><div className="context-links"><Link to={`/transactions/${alert.transaction_id}`}>Open transaction workspace</Link><Link to="/cases">Open cases workspace</Link></div></Card></aside></div></>;
}
