import type { ApiRequestOptions } from "../types/api";
import type {
  AlertListResponse,
  AlertDetail,
  Alert,
  CaseRead,
  CaseDetail,
  CaseComment,
  CaseListResponse,
  DashboardDistribution,
  DashboardSummary,
  RuleAlertCount,
  RuleConfiguration,
  MonitoringRunResponse,
  TransactionImportResponse,
  TransactionDetail,
  TransactionListResponse,
  TrendPoint,
  AIEnrichment,
  LLMAssistance,
  RuleCoverageItem,
} from "../types/api";

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

function buildUrl(path: string, query?: ApiRequestOptions["query"]): string {
  const base = API_BASE_URL.startsWith("http")
    ? API_BASE_URL
    : `${window.location.origin}${API_BASE_URL}`;
  const url = new URL(`${base}${path.startsWith("/") ? path : `/${path}`}`);
  Object.entries(query ?? {}).forEach(([key, value]) => {
    if (value !== undefined) url.searchParams.set(key, String(value));
  });
  return url.toString();
}

export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
  const { query, headers, ...requestOptions } = options;
  const response = await fetch(buildUrl(path, query), {
    ...requestOptions,
    headers: { Accept: "application/json", ...headers },
  });

  if (!response.ok) {
    const body = await response.text();
    let message = body || `Request failed with status ${response.status}`;
    try {
      const parsed = JSON.parse(body) as { error?: { message?: string } };
      message = parsed.error?.message ?? message;
    } catch {
      // Preserve the response text when the server does not return JSON.
    }
    throw new Error(message);
  }

  return (await response.json()) as T;
}

export const api = {
  getDashboardSummary: (query?: ApiRequestOptions["query"]) =>
    apiRequest<DashboardSummary>("/dashboard/summary", { query }),
  getTransactionTrend: (timeRange: string) =>
    apiRequest<TrendPoint[]>("/dashboard/transactions/trend", {
      query: { time_range: timeRange },
    }),
  getAlertTrend: (timeRange: string) =>
    apiRequest<TrendPoint[]>("/dashboard/alerts/trend", {
      query: { time_range: timeRange },
    }),
  getTopRules: () => apiRequest<RuleAlertCount[]>("/dashboard/rules/top"),
  getDistributions: () => apiRequest<DashboardDistribution>("/dashboard/distributions"),
  getRules: () => apiRequest<RuleConfiguration[]>("/rules"),
  getRule: (ruleCode: string) => apiRequest<RuleConfiguration>(`/rules/${encodeURIComponent(ruleCode)}`),
  updateRule: (ruleCode: string, changes: Partial<Pick<RuleConfiguration, "enabled" | "priority" | "risk_level">> & { parameters?: Record<string, unknown> }) =>
    apiRequest<RuleConfiguration>(`/rules/${encodeURIComponent(ruleCode)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(changes),
    }),
  getAlerts: (query?: ApiRequestOptions["query"]) =>
    apiRequest<AlertListResponse>("/alerts", { query }),
  getAlert: (alertId: string) => apiRequest<AlertDetail>(`/alerts/${encodeURIComponent(alertId)}`),
  getAIEnrichment: (transactionId: number) =>
    apiRequest<AIEnrichment>(`/transactions/${transactionId}/ai-enrichment`),
  generateAIAssistance: (alertId: number) =>
    apiRequest<LLMAssistance>(`/alerts/${alertId}/ai-assistance`, { method: "POST" }),
  updateAlertStatus: (alertId: number, status: string) =>
    apiRequest<Alert>(`/alerts/${alertId}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }),
  updateAlertPriority: (alertId: number, priority: number) =>
    apiRequest<Alert>(`/alerts/${alertId}/priority`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ priority }) }),
  updateAlertAssignment: (alertId: number, assignedTo: string | null) =>
    apiRequest<Alert>(`/alerts/${alertId}/assignment`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assigned_to: assignedTo }) }),
  createCaseFromAlert: (alertId: number) =>
    apiRequest<CaseRead>(`/alerts/${alertId}/case`, { method: "POST" }),
  getCases: (query?: ApiRequestOptions["query"]) =>
    apiRequest<CaseListResponse>("/cases", { query }),
  getCase: (caseId: string) => apiRequest<CaseDetail>(`/cases/${encodeURIComponent(caseId)}`),
  updateCaseStatus: (caseId: number, status: string) =>
    apiRequest<CaseRead>(`/cases/${caseId}/status`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status }) }),
  updateCasePriority: (caseId: number, priority: number) =>
    apiRequest<CaseRead>(`/cases/${caseId}/priority`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ priority }) }),
  updateCaseAssignment: (caseId: number, assignedTo: string | null) =>
    apiRequest<CaseRead>(`/cases/${caseId}/assignment`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ assigned_to: assignedTo }) }),
  getCaseComments: (caseId: string) => apiRequest<CaseComment[]>(`/cases/${encodeURIComponent(caseId)}/comments`),
  addCaseComment: (caseId: number, comment: string, createdBy: string) =>
    apiRequest<CaseComment>(`/cases/${caseId}/comments`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ comment, created_by: createdBy }) }),
  getTransactions: (query?: ApiRequestOptions["query"]) =>
    apiRequest<TransactionListResponse>("/transactions", { query }),
  importTransactions: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return apiRequest<TransactionImportResponse>("/transactions/import", {
      method: "POST",
      body,
    });
  },
  runMonitoring: () => apiRequest<MonitoringRunResponse>("/monitoring/run", { method: "POST" }),
  getRuleCoverage: () => apiRequest<RuleCoverageItem[]>("/monitoring/rule-coverage"),
  importTransactionsEnhanced: (file: File, skiprows: number = 0) => {
    const body = new FormData();
    body.append("file", file);
    return apiRequest<TransactionImportResponse>("/transactions/import-enhanced", {
      method: "POST",
      body,
      query: { skiprows: String(skiprows) },
    });
  },
  getTransaction: (transactionId: string) =>
    apiRequest<TransactionDetail>(`/transactions/${encodeURIComponent(transactionId)}`),
};
