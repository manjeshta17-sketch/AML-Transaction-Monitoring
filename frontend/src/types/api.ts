export type ApiRequestOptions = RequestInit & {
  query?: Record<string, string | number | boolean | undefined>;
};

export interface ApiError {
  error?: {
    code?: string;
    message?: string;
    details?: unknown;
  };
}

export interface TrendPoint {
  bucket: string;
  count: number;
}

export interface DashboardSummary {
  time_range: string | null;
  date_from: string | null;
  date_to: string | null;
  transactions: {
    total_transactions: number;
    total_transaction_amount: number;
    transaction_types: Record<string, number>;
  };
  alerts: {
    total_alerts: number;
    open_alerts: number;
    closed_alerts: number;
    by_rule: Record<string, number>;
    by_priority: Record<string, number>;
    by_risk_level: Record<string, number>;
  };
  cases: {
    total_cases: number;
    by_status: Record<string, number>;
    by_priority: Record<string, number>;
    assigned_cases: number;
    unassigned_cases: number;
  };
  high_priority_alerts: number;
  high_priority_cases: number;
}

export interface RuleAlertCount {
  rule_code: string;
  rule_name: string;
  alert_count: number;
}

export interface DashboardDistribution {
  alerts_by_risk_level: Record<string, number>;
  alerts_by_priority: Record<string, number>;
  cases_by_priority: Record<string, number>;
}

export interface RuleConfiguration {
  id: number;
  rule_code: string;
  name: string;
  description: string;
  enabled: boolean;
  category: string;
  risk_level: string;
  priority: number;
  parameters: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface TransactionImportResponse {
  message: string;
  import_id: number;
  source_filename: string | null;
  rows_processed: number;
  records_imported: number;
  duplicates_skipped: number;
  status: string;
  validation?: ValidationResult;
}

export interface ValidationResult {
  total_rows: number;
  valid_rows: number;
  invalid_rows: number;
  missing_required_fields: Record<string, number>;
  missing_optional_fields: Record<string, number>;
  unknown_columns: string[];
  invalid_data_types: Record<string, number>;
  invalid_dates: Record<string, number>;
  invalid_amounts: number;
  unsupported_transaction_types: Record<string, number>;
  column_mapping: Record<string, string>;
}

export interface MonitoringRunResponse {
  transactions_evaluated: number;
  alerts_generated: number;
  alerts_by_rule: Record<string, number>;
  insufficient_history: Array<{
    rule_code: string;
    entity_field: string;
    entity_value: string | null;
    evaluation_month: string;
    required_months: number;
    available_months: number;
    reason: string;
  }>;
  data_insufficient: Array<{
    rule_code: string;
    required_fields: string[];
    missing_fields: string[];
    reason: string;
  }>;
}

export interface Alert {
  id: number;
  alert_code: string;
  rule_code: string;
  rule_name: string;
  description: string | null;
  transaction_id: number;
  customer_id: string | null;
  card_number: string | null;
  amount: number | null;
  risk_level: string;
  priority: number;
  status: string;
  assigned_to: string | null;
  created_at: string;
  updated_at: string;
}

export interface AlertListResponse {
  alerts: Alert[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AlertDetail extends Alert {
  transaction: {
    id: number;
    ext_txn_id: string | null;
    transaction_type: string | null;
    amount: number | null;
    txn_date: string | null;
    customer_id: string | null;
    card_number: string | null;
  } | null;
}

export type AIEnrichmentStatus = "AVAILABLE" | "INSUFFICIENT_HISTORY" | "UNAVAILABLE" | "ERROR";

export interface AIEnrichment {
  transaction_id: number;
  model_version: string;
  feature_pipeline_version: string;
  anomaly_score: number | null;
  anomaly_flag: boolean | null;
  history_sufficient: boolean;
  enrichment_status: AIEnrichmentStatus;
  generated_at: string;
}

export type LLMAssistanceStatus =
  | "VALID"
  | "CREDENTIALS_UNAVAILABLE"
  | "PROVIDER_UNAVAILABLE"
  | "TIMEOUT"
  | "ERROR"
  | "INVALID";

export interface LLMAssistance {
  id: number;
  alert_id: number;
  provider: string;
  model: string | null;
  prompt_version: string;
  response_status: LLMAssistanceStatus;
  validated: boolean;
  generated_response: string | null;
  generated_at: string;
  latency_ms: number | null;
}

export interface CaseRead {
  id: number;
  case_code: string;
  status: string;
  priority: number;
  assigned_to: string | null;
  alert_id: number;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
}

export interface CaseComment {
  id: number;
  case_id: number;
  comment: string;
  created_by: string;
  created_at: string;
}

export interface CaseListResponse {
  cases: CaseRead[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface CaseDetail extends CaseRead {
  alert: {
    id: number;
    alert_code: string;
    rule_code: string;
    rule_name: string;
    description: string | null;
    transaction_id: number;
    customer_id: string | null;
    amount: number | null;
    priority: number;
    status: string;
  } | null;
  transaction: {
    id: number;
    ext_txn_id: string | null;
    transaction_type: string | null;
    amount: number | null;
    txn_date: string | null;
    customer_id: string | null;
    card_number: string | null;
  } | null;
  comments: CaseComment[];
}

export interface Transaction {
  id: number;
  txn_date: string | null;
  corporate_name: string | null;
  proxy_card_number: string | null;
  card_number: string | null;
  rrn: string | null;
  auth_code: string | null;
  ext_txn_id: string | null;
  amount: number | null;
  transaction_type: string | null;
  status: string | null;
  customer_id: string | null;
  post_wallet_balance: number | null;
  cr_dr_flag: string | null;
  other_party_id: string | null;
  other_party_name: string | null;
  currency: string | null;
  home_currency: string | null;
  country_code: string | null;
  domestic_status: string | null;
  load_source: string | null;
  settlement_currency: string | null;
  originating_country_currency: string | null;
  product: string | null;
  txn_amount: number | null;
  fees: number | null;
  description: string | null;
  mcc: string | null;
  activation_date: string | null;
}

export interface TransactionListResponse {
  transactions: Transaction[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface TransactionAlertSummary {
  id: number;
  alert_code: string;
  rule_code: string;
}

export interface TransactionCaseSummary {
  id: number;
  case_code: string;
  status: string;
}

export interface TransactionDetail extends Transaction {
  alert_count: number;
  alerts: TransactionAlertSummary[];
  cases: TransactionCaseSummary[];
}

export interface RuleCoverageItem {
  rule_code: string;
  rule_name: string;
  category: string;
  has_sufficient_data: boolean;
  reason: string | null;
  alerts_generated: number;
}
