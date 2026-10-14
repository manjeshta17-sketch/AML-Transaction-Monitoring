import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../layouts/AppShell";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { DashboardPage } from "../pages/DashboardPage";
import { TransactionDetailPage } from "../pages/TransactionDetailPage";
import { TransactionsPage } from "../pages/TransactionsPage";
import { AlertsPage } from "../pages/AlertsPage";
import { AlertDetailPage } from "../pages/AlertDetailPage";
import { CasesPage } from "../pages/CasesPage";
import { CaseDetailPage } from "../pages/CaseDetailPage";
import { RulesPage } from "../pages/RulesPage";
import { RuleDetailPage } from "../pages/RuleDetailPage";
import { FileProcessingPage } from "../pages/FileProcessingPage";

const pages = [
  ["dashboard", "Dashboard", "A focused overview of monitoring operations."],
  ["transactions", "Transactions", "Search and review transaction activity."],
  ["alerts", "Alerts", "Prioritize and work monitoring alerts."],
  ["cases", "Cases", "Manage investigation cases and outcomes."],
  ["rules", "Rules", "Review configured monitoring rules."],
  ["file-processing", "File Processing", "Import and monitor transaction report processing."],
  ["reports", "Reports", "Access operational monitoring reports."],
] as const;

export function AppRoutes() {
  return <Routes><Route element={<AppShell />}>
    <Route path="/" element={<Navigate to="/dashboard" replace />} />
    <Route path="/dashboard" element={<DashboardPage />} />
    <Route path="/transactions" element={<TransactionsPage />} />
    <Route path="/transactions/:transactionId" element={<TransactionDetailPage />} />
    <Route path="/alerts" element={<AlertsPage />} />
    <Route path="/alerts/:alertId" element={<AlertDetailPage />} />
    <Route path="/cases" element={<CasesPage />} />
    <Route path="/cases/:caseId" element={<CaseDetailPage />} />
    <Route path="/rules" element={<RulesPage />} />
    <Route path="/rules/:ruleCode" element={<RuleDetailPage />} />
    <Route path="/file-processing" element={<FileProcessingPage />} />
    {pages.filter(([path]) => !["dashboard", "file-processing"].includes(path)).map(([path, title, description]) => <Route key={path} path={`/${path}`} element={<PlaceholderPage title={title} description={description} />} />)}
  </Route></Routes>;
}
