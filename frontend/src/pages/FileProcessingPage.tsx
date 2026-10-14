import { ChangeEvent, DragEvent, useRef, useState } from "react";
import { Card } from "../components/Card";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { api } from "../services/apiClient";
import type { MonitoringRunResponse, TransactionImportResponse, ValidationResult, RuleCoverageItem } from "../types/api";

type Stage = "idle" | "selected" | "imported" | "monitoring" | "monitored" | "coverage";

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function isSupportedFile(file: File) {
  const ext = file.name.toLowerCase();
  return ext.endsWith(".csv") || ext.endsWith(".xls") || ext.endsWith(".xlsx");
}

function Workflow({ stage }: { stage: Stage }) {
  const steps = [
    ["selected", "File selected"],
    ["imported", "Import / validate"],
    ["monitored", "Monitoring"],
    ["monitored", "Alerts"],
    ["coverage", "Rule coverage"],
  ] as const;
  return <ol className="processing-workflow" aria-label="File processing workflow">{steps.map(([key, label], index) => {
    const active = stage === key || (key === "selected" && stage !== "idle") || (key === "imported" && ["imported", "monitoring", "monitored", "coverage"].includes(stage)) || (key === "monitored" && ["monitored", "coverage"].includes(stage)) || (key === "coverage" && stage === "coverage");
    return <li className={active ? "complete" : ""} key={`${key}-${label}`}><span>{active ? "✓" : index + 1}</span><strong>{label}</strong></li>;
  })}</ol>;
}

function ImportResult({ result }: { result: TransactionImportResponse }) {
  return <div className="processing-result" role="status"><strong>{result.message}</strong><dl className="result-metrics"><div><dt>Import ID</dt><dd>#{result.import_id}</dd></div><div><dt>Rows processed</dt><dd>{result.rows_processed.toLocaleString()}</dd></div><div><dt>Records imported</dt><dd>{result.records_imported.toLocaleString()}</dd></div><div><dt>Duplicates skipped</dt><dd>{result.duplicates_skipped.toLocaleString()}</dd></div><div><dt>Source file</dt><dd>{result.source_filename ?? "—"}</dd></div><div><dt>Status</dt><dd>{result.status}</dd></div></dl>{result.validation && <ValidationDetails validation={result.validation} />}</div>;
}

function ValidationDetails({ validation }: { validation: ValidationResult }) {
  const missingRequiredList = Object.entries(validation.missing_required_fields).map(([field, count]) => `${field}: ${count}`).join(", ");
  const missingOptionalList = Object.entries(validation.missing_optional_fields).map(([field, count]) => `${field}: ${count}`).join(", ");
  return <div className="validation-details"><h3>Validation Summary</h3><dl className="result-metrics"><div><dt>Total rows</dt><dd>{validation.total_rows.toLocaleString()}</dd></div><div><dt>Valid rows</dt><dd>{validation.valid_rows.toLocaleString()}</dd></div><div><dt>Invalid rows</dt><dd>{validation.invalid_rows.toLocaleString()}</dd></div></dl>{validation.invalid_rows > 0 && <div className="validation-errors"><h4>Validation Issues</h4>{Object.keys(validation.missing_required_fields).length > 0 && <div><strong>Missing required fields:</strong> {missingRequiredList}</div>}{Object.keys(validation.missing_optional_fields).length > 0 && <div><strong>Missing optional fields:</strong> {missingOptionalList}</div>}{validation.unknown_columns.length > 0 && <div><strong>Unknown columns ignored:</strong> {validation.unknown_columns.join(", ")}</div>}{validation.invalid_amounts > 0 && <div><strong>Invalid amounts:</strong> {validation.invalid_amounts.toLocaleString()}</div>}</div>}</div>;
}

function RuleCoverageList({ items }: { items: RuleCoverageItem[] }) {
  return <div className="processing-result" role="status"><strong>AML Rule Coverage</strong><p className="processing-note">Which R001-R016 rules have sufficient data to run after this import.</p><div className="processing-list">{items.map((item) => <div key={item.rule_code} className="rule-coverage-item"><span className={item.has_sufficient_data ? "rule-sufficient" : "rule-insufficient"}>{item.rule_code}: {item.rule_name}</span><span>{item.has_sufficient_data ? "✓ Sufficient data" : `✗ ${item.reason || "Insufficient data"}`}</span></div>)}</div></div>;
}

function MonitoringResult({ result }: { result: MonitoringRunResponse }) {
  return <div className="processing-result" role="status"><strong>Monitoring completed</strong><dl className="result-metrics"><div><dt>Transactions evaluated</dt><dd>{result.transactions_evaluated.toLocaleString()}</dd></div><div><dt>Alerts generated</dt><dd>{result.alerts_generated.toLocaleString()}</dd></div></dl>{Object.keys(result.alerts_by_rule).length > 0 && <div className="processing-list"><h3>Alerts by rule</h3>{Object.entries(result.alerts_by_rule).map(([rule, count]) => <div key={rule}><span>{rule}</span><strong>{count.toLocaleString()}</strong></div>)}</div>}{result.insufficient_history.length > 0 && <p className="processing-note">{result.insufficient_history.length} historical evaluation(s) lacked sufficient history.</p>}{result.data_insufficient.length > 0 && <p className="processing-note">{result.data_insufficient.length} rule evaluation(s) lacked required data.</p>}</div>;
}

export function FileProcessingPage() {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<Stage>("idle");
  const [importResult, setImportResult] = useState<TransactionImportResponse | null>(null);
  const [monitoringResult, setMonitoringResult] = useState<MonitoringRunResponse | null>(null);
  const [ruleCoverage, setRuleCoverage] = useState<RuleCoverageItem[] | null>(null);
  const [loading, setLoading] = useState<"import" | "monitoring" | "coverage" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const chooseFile = (candidate: File | undefined) => {
    if (!candidate) return;
    if (!isSupportedFile(candidate)) { setError("Select a CSV, XLS, or XLSX file to continue."); setFile(null); setStage("idle"); return; }
    setError(null); setImportResult(null); setMonitoringResult(null); setRuleCoverage(null); setFile(candidate); setStage("selected");
  };
  const onInput = (event: ChangeEvent<HTMLInputElement>) => chooseFile(event.target.files?.[0]);
  const onDrop = (event: DragEvent<HTMLDivElement>) => { event.preventDefault(); chooseFile(event.dataTransfer.files[0]); };
  const clear = () => { setFile(null); setStage("idle"); setError(null); setImportResult(null); setMonitoringResult(null); setRuleCoverage(null); if (inputRef.current) inputRef.current.value = ""; };
  const importFile = async () => {
    if (!file) { setError("Select a file before importing."); return; }
    setLoading("import"); setError(null); setMonitoringResult(null); setRuleCoverage(null);
    try { setImportResult(await api.importTransactionsEnhanced(file, 0)); setStage("imported"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "The file could not be imported."); }
    finally { setLoading(null); }
  };
  const runMonitoring = async () => {
    setLoading("monitoring"); setError(null); setStage("monitoring");
    try { setMonitoringResult(await api.runMonitoring()); setStage("monitored"); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Monitoring could not be completed."); setStage("imported"); }
    finally { setLoading(null); }
  };
  const checkRuleCoverage = async () => {
    setLoading("coverage"); setError(null); setStage("coverage");
    try { setRuleCoverage(await api.getRuleCoverage()); }
    catch (reason) { setError(reason instanceof Error ? reason.message : "Could not retrieve rule coverage."); setStage("monitored"); }
    finally { setLoading(null); }
  };
  return <><PageHeader eyebrow="Operations workspace" title="File Processing" description="Validate and import daily transaction files (CSV, XLS, XLSX), then run monitoring to identify resulting alerts and check AML rule coverage." /><Workflow stage={stage} /><div className="processing-layout"><Card><div className="section-heading"><div><h2>Daily transaction import</h2><p>Upload CSV, XLS, or XLSX reports. Report headers and common CSV delimiters are detected automatically before column mapping and validation.</p></div></div><div className={`upload-dropzone ${file ? "has-file" : ""}`} onDragOver={(event) => event.preventDefault()} onDrop={onDrop}><input ref={inputRef} className="visually-hidden" id="transaction-file" type="file" accept=".csv,.xls,.xlsx" onChange={onInput} /><p><strong>{file ? file.name : "Select a file"}</strong></p><p>{file ? formatBytes(file.size) : "Choose a CSV, XLS, or XLSX file or drag it into this area. Imports are limited to 25 MB and begin only when you select Import File."}</p><button className="secondary-button" type="button" onClick={() => inputRef.current?.click()} disabled={loading !== null}>{file ? "Choose another file" : "Choose file"}</button></div>{file && <div className="selected-file"><div><strong>{file.name}</strong><span>{formatBytes(file.size)}</span></div><button className="text-button" type="button" onClick={clear} disabled={loading !== null}>Remove</button></div>}<div className="filter-actions"><button className="primary-button" type="button" onClick={() => void importFile()} disabled={!file || loading !== null}>{loading === "import" ? "Importing…" : "Import File"}</button>{loading === "import" && <LoadingState />}</div></Card><Card><div className="section-heading"><div><h2>Processing status</h2><p>Import results, monitoring runs, and rule coverage from this page session.</p></div></div>{error && <><ErrorState message={error} /></>}{!error && !importResult && <p className="processing-note">Select and import a file to begin processing.</p>}{importResult && <ImportResult result={importResult} />}{importResult && !monitoringResult && <button className="primary-button" type="button" onClick={() => void runMonitoring()} disabled={loading !== null}>{loading === "monitoring" ? "Running monitoring…" : "Run Monitoring"}</button>}{monitoringResult && <MonitoringResult result={monitoringResult} />}{monitoringResult && !ruleCoverage && <button className="primary-button" type="button" onClick={() => void checkRuleCoverage()} disabled={loading !== null}>{loading === "coverage" ? "Checking coverage…" : "Check AML Rule Coverage"}</button>}{ruleCoverage && <RuleCoverageList items={ruleCoverage} />}</Card></div></>;
}
