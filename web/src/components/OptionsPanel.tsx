"use client";

import { useState } from "react";
import {
  CheckCircle2,
  XCircle,
  DollarSign,
  Shield,
  FileCode,
  Download,
  GitBranch,
  Loader2,
  AlertTriangle,
  TrendingUp,
  ClipboardList,
  Plus,
  Minus,
  RefreshCw,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { api } from "@/lib/api";

interface SecurityIssue {
  severity: string;
  rule_id: string;
  description: string;
  file_path?: string;
  line_number?: number;
  scanner?: string;
}

interface OptionsPanelProps {
  files: Record<string, string>;
  onComplete: (type: string, result: unknown) => void;
  initialSecurityIssues?: SecurityIssue[];
  initialCostEstimate?: {
    monthly_cost: string | number;
    breakdown?: Array<{ name: string; monthly_cost: string | number }>;
  };
}

interface CostItem {
  name: string;
  monthly_cost: string | number;
}

// Severity badge colors
const severityColors: Record<string, string> = {
  CRITICAL: "bg-red-600 text-white",
  HIGH: "bg-red-500 text-white",
  MEDIUM: "bg-yellow-500 text-black",
  LOW: "bg-blue-500 text-white",
  INFO: "bg-gray-500 text-white",
};

// Extract just the filename from a path
function getFileName(filePath?: string): string {
  if (!filePath) return "-";
  const parts = filePath.split("/");
  return parts[parts.length - 1] || filePath;
}

// Scanner summary component
function ScannerSummary({ issues, hasScanned }: { issues: SecurityIssue[]; hasScanned: boolean }) {
  const scanners = [
    { id: "tfsec", name: "tfsec", description: "Static analysis" },
    { id: "checkov", name: "Checkov", description: "Policy checks" },
    { id: "conftest", name: "Conftest", description: "OPA policies" },
  ];

  const getIssueCount = (scannerId: string) =>
    issues.filter(i => (i.scanner || "tfsec") === scannerId).length;

  const getHighSeverityCount = (scannerId: string) =>
    issues.filter(i => (i.scanner || "tfsec") === scannerId &&
      (i.severity === "CRITICAL" || i.severity === "HIGH")).length;

  if (!hasScanned) return null;

  return (
    <div className="grid grid-cols-3 gap-2 mb-3">
      {scanners.map((scanner) => {
        const count = getIssueCount(scanner.id);
        const highCount = getHighSeverityCount(scanner.id);
        return (
          <div
            key={scanner.id}
            className={`p-2 rounded-lg border text-center ${
              count === 0
                ? "border-green-500/30 bg-green-500/5"
                : highCount > 0
                ? "border-red-500/30 bg-red-500/5"
                : "border-yellow-500/30 bg-yellow-500/5"
            }`}
          >
            <div className="text-xs font-medium">{scanner.name}</div>
            <div className="text-[10px] text-muted-foreground">{scanner.description}</div>
            <div className={`text-sm font-bold mt-1 ${
              count === 0 ? "text-green-500" : highCount > 0 ? "text-red-500" : "text-yellow-500"
            }`}>
              {count === 0 ? "✓ Pass" : `${count} issue${count > 1 ? "s" : ""}`}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function SecurityIssuesTable({ issues, hasScanned }: { issues: SecurityIssue[]; hasScanned: boolean }) {
  // Sort by severity
  const severityOrder = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
  const sortedIssues = [...issues].sort((a, b) => {
    return severityOrder.indexOf(a.severity) - severityOrder.indexOf(b.severity);
  });

  return (
    <div className="space-y-3">
      {/* Scanner Summary */}
      <ScannerSummary issues={issues} hasScanned={hasScanned} />

      {issues.length === 0 ? (
        <div className="flex items-center gap-2 text-green-500 py-2">
          <CheckCircle2 className="h-5 w-5" />
          <span className="font-medium">All security checks passed</span>
        </div>
      ) : (
        <>
          {/* Issue Summary */}
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted-foreground">
              Found <span className="font-bold text-red-500">{issues.length}</span> issue(s)
            </span>
            {issues.filter(i => i.severity === "CRITICAL" || i.severity === "HIGH").length > 0 && (
              <span className="text-red-500 font-medium">
                {issues.filter(i => i.severity === "CRITICAL" || i.severity === "HIGH").length} critical/high
              </span>
            )}
          </div>

      {/* Table */}
      <div className="border border-zinc-800 rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-zinc-900 text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Severity</th>
                <th className="px-3 py-2 font-medium">Rule ID</th>
                <th className="px-3 py-2 font-medium">Description</th>
                <th className="px-3 py-2 font-medium">File:Line</th>
                <th className="px-3 py-2 font-medium">Scanner</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-800">
              {sortedIssues.map((issue, i) => (
                <tr key={i} className="hover:bg-zinc-900/50">
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-medium ${severityColors[issue.severity] || severityColors.MEDIUM}`}>
                      {issue.severity}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-muted-foreground">
                    {issue.rule_id}
                  </td>
                  <td className="px-3 py-2 max-w-[300px]">
                    <span className="line-clamp-2" title={issue.description}>
                      {issue.description}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-mono text-muted-foreground whitespace-nowrap">
                    {getFileName(issue.file_path)}
                    {issue.line_number ? `:${issue.line_number}` : ""}
                  </td>
                  <td className="px-3 py-2 text-muted-foreground">
                    {issue.scanner || "tfsec"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
        </>
      )}
    </div>
  );
}

function CostBreakdown({ cost }: { cost: { monthly_cost: string | number; breakdown: CostItem[] } }) {
  // Parse the total cost to a number (handle both string and number)
  const monthlyCostStr = typeof cost.monthly_cost === 'number'
    ? cost.monthly_cost.toString()
    : cost.monthly_cost || '0';
  const totalCost = parseFloat(monthlyCostStr.replace(/[^0-9.]/g, "")) || 0;

  // Group similar resources and calculate max cost for bar scaling
  const breakdown = cost.breakdown || [];
  const parseCost = (val: string | number) => typeof val === 'number' ? val : parseFloat(val) || 0;
  const maxCost = Math.max(...breakdown.map((item) => parseCost(item.monthly_cost)), 1);

  // Shorten resource names for display
  const shortenName = (name: string) => {
    // Remove common prefixes and extract resource type + name
    const parts = name.split(".");
    if (parts.length >= 2) {
      const resourceType = parts[0].replace("aws_", "").replace("azurerm_", "").replace("google_", "");
      const resourceName = parts.slice(1).join(".");
      // Truncate if too long
      const shortName = resourceName.length > 20 ? resourceName.slice(0, 20) + "..." : resourceName;
      return `${resourceType}: ${shortName}`;
    }
    return name.length > 30 ? name.slice(0, 30) + "..." : name;
  };

  // Group by resource type for summary
  const byType: Record<string, number> = {};
  breakdown.forEach((item) => {
    const parts = item.name.split(".");
    const resourceType = parts[0]?.replace("aws_", "").replace("azurerm_", "").replace("google_", "") || "other";
    byType[resourceType] = (byType[resourceType] || 0) + parseCost(item.monthly_cost);
  });

  const sortedTypes = Object.entries(byType)
    .sort(([, a], [, b]) => b - a)
    .slice(0, 5);

  return (
    <div className="space-y-4">
      {/* Total Cost Header */}
      <div className="flex items-center justify-between p-3 rounded-lg bg-gradient-to-r from-green-500/10 to-emerald-500/10 border border-green-500/20">
        <div>
          <div className="text-xs text-muted-foreground">Estimated Monthly Cost</div>
          <div className="text-3xl font-bold text-green-500">
            {typeof cost.monthly_cost === 'number'
              ? `$${cost.monthly_cost.toFixed(2)}`
              : cost.monthly_cost}
          </div>
        </div>
        <div className="text-right">
          <div className="text-xs text-muted-foreground">Yearly</div>
          <div className="text-lg font-semibold text-muted-foreground">
            ${(totalCost * 12).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>
      </div>

      {/* Cost by Resource Type */}
      {sortedTypes.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center gap-1 text-xs font-medium text-muted-foreground">
            <TrendingUp className="h-3 w-3" />
            Top Cost Drivers
          </div>
          <div className="space-y-2">
            {sortedTypes.map(([type, typeCost]) => (
              <div key={type} className="space-y-1">
                <div className="flex items-center justify-between text-xs">
                  <span className="capitalize">{type.replace(/_/g, " ")}</span>
                  <span className="font-medium">${typeCost.toFixed(2)}</span>
                </div>
                <div className="h-2 w-full rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-green-500 to-emerald-500 transition-all duration-500"
                    style={{ width: `${Math.min((typeCost / totalCost) * 100, 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Detailed Breakdown */}
      {breakdown.length > 0 && (
        <div className="space-y-2">
          <div className="text-xs font-medium text-muted-foreground">
            All Resources ({breakdown.length})
          </div>
          <div className="max-h-[200px] overflow-y-auto space-y-1 pr-2 scrollbar-thin">
            {breakdown
              .sort((a, b) => parseCost(b.monthly_cost) - parseCost(a.monthly_cost))
              .map((item, i) => {
                const itemCost = parseCost(item.monthly_cost);
                const displayCost = typeof item.monthly_cost === 'number'
                  ? item.monthly_cost.toFixed(2)
                  : item.monthly_cost;
                return (
                  <div
                    key={i}
                    className="flex items-center justify-between py-1 px-2 rounded text-xs hover:bg-zinc-800/50 group"
                    title={item.name}
                  >
                    <span className="text-muted-foreground truncate max-w-[180px]">
                      {shortenName(item.name)}
                    </span>
                    <div className="flex items-center gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                        <div
                          className="h-full rounded-full bg-green-500/60"
                          style={{ width: `${(itemCost / maxCost) * 100}%` }}
                        />
                      </div>
                      <span className="font-medium w-16 text-right">${displayCost}</span>
                    </div>
                  </div>
                );
              })}
          </div>
        </div>
      )}
    </div>
  );
}

export function OptionsPanel({
  files,
  onComplete,
  initialSecurityIssues,
  initialCostEstimate,
}: OptionsPanelProps) {
  const [validating, setValidating] = useState(false);
  const [validation, setValidation] = useState<{
    valid: boolean;
    errors: string[];
    warnings: string[];
  } | null>(null);

  const [estimating, setEstimating] = useState(false);
  const [cost, setCost] = useState<{
    monthly_cost: string | number;
    breakdown: Array<{ name: string; monthly_cost: string | number }>;
  } | null>(initialCostEstimate ? { ...initialCostEstimate, breakdown: initialCostEstimate.breakdown || [] } : null);

  const [scanning, setScanning] = useState(false);
  // Only consider scanned if initialSecurityIssues is an actual array (not undefined)
  const [hasScanned, setHasScanned] = useState(Array.isArray(initialSecurityIssues));
  const [securityIssues, setSecurityIssues] = useState<SecurityIssue[]>(
    initialSecurityIssues || []
  );

  const [planning, setPlanning] = useState(false);
  const [planResult, setPlanResult] = useState<{
    success: boolean;
    plan_output?: string;
    resource_changes?: Array<{
      address: string;
      type: string;
      name: string;
      actions: string[];
    }>;
    error?: string;
  } | null>(null);

  const handleValidate = async () => {
    setValidating(true);
    try {
      const result = await api.validate(files);
      setValidation(result);
      onComplete("validate", result);
    } catch (error) {
      console.error("Validation error:", error);
    } finally {
      setValidating(false);
    }
  };

  const handleEstimateCost = async () => {
    setEstimating(true);
    try {
      const result = await api.estimateCost(files);
      if (result.monthly_cost) {
        setCost({
          monthly_cost: result.monthly_cost,
          breakdown: result.breakdown || [],
        });
        onComplete("cost", result);
      }
    } catch (error) {
      console.error("Cost estimation error:", error);
    } finally {
      setEstimating(false);
    }
  };

  const handleSecurityScan = async () => {
    setScanning(true);
    try {
      const result = await api.securityScan(files);
      // Convert to SecurityIssue format
      const issues: SecurityIssue[] = (result.issues || []).map((issue: Record<string, unknown>) => ({
        severity: issue.severity as string || "MEDIUM",
        rule_id: issue.rule_id as string || "",
        description: issue.description as string || "",
        file_path: issue.file_path as string,
        line_number: issue.line_number as number,
        scanner: issue.scanner as string || "tfsec",
      }));
      setSecurityIssues(issues);
      setHasScanned(true);
      onComplete("security", result);
    } catch (error) {
      console.error("Security scan error:", error);
    } finally {
      setScanning(false);
    }
  };

  const handlePlan = async () => {
    setPlanning(true);
    setPlanResult(null);
    try {
      const result = await api.plan(files);
      setPlanResult(result);
      onComplete("plan", result);
    } catch (error) {
      console.error("Plan error:", error);
      setPlanResult({
        success: false,
        error: error instanceof Error ? error.message : "Plan failed",
      });
    } finally {
      setPlanning(false);
    }
  };

  const handleDownload = () => {
    // Create a simple zip-like download (multiple files)
    Object.entries(files).forEach(([name, content]) => {
      const blob = new Blob([content], { type: "text/plain" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = name;
      a.click();
      URL.revokeObjectURL(url);
    });
  };

  return (
    <Card className="mt-4 bg-background">
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">
          Review Before Deploying
        </CardTitle>
      </CardHeader>
      <CardContent>
        <Tabs defaultValue="validate" className="w-full">
          <TabsList className="grid w-full grid-cols-5">
            <TabsTrigger value="validate" className="text-xs">
              <CheckCircle2 className="mr-1 h-3 w-3" />
              Validate
            </TabsTrigger>
            <TabsTrigger value="plan" className="text-xs">
              <ClipboardList className="mr-1 h-3 w-3" />
              Plan
            </TabsTrigger>
            <TabsTrigger value="cost" className="text-xs">
              <DollarSign className="mr-1 h-3 w-3" />
              Cost
            </TabsTrigger>
            <TabsTrigger value="security" className="text-xs">
              <Shield className="mr-1 h-3 w-3" />
              Security
            </TabsTrigger>
            <TabsTrigger value="export" className="text-xs">
              <FileCode className="mr-1 h-3 w-3" />
              Export
            </TabsTrigger>
          </TabsList>

          <TabsContent value="validate" className="mt-4">
            {!validation ? (
              <Button
                onClick={handleValidate}
                disabled={validating}
                className="w-full"
                variant="outline"
              >
                {validating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <CheckCircle2 className="mr-2 h-4 w-4" />
                )}
                Run Terraform Validate
              </Button>
            ) : (
              <div className="space-y-2">
                <div
                  className={`flex items-center gap-2 ${
                    validation.valid ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {validation.valid ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <span className="text-sm font-medium">
                    {validation.valid
                      ? "Validation passed"
                      : "Validation failed"}
                  </span>
                </div>
                {validation.errors.length > 0 && (
                  <ul className="space-y-1 text-xs text-red-500">
                    {validation.errors.map((err, i) => (
                      <li key={i}>{err}</li>
                    ))}
                  </ul>
                )}
                {validation.warnings.length > 0 && (
                  <ul className="space-y-1 text-xs text-yellow-500">
                    {validation.warnings.map((warn, i) => (
                      <li key={i}>{warn}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </TabsContent>

          <TabsContent value="plan" className="mt-4">
            {!planResult ? (
              <Button
                onClick={handlePlan}
                disabled={planning}
                className="w-full"
                variant="outline"
              >
                {planning ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <ClipboardList className="mr-2 h-4 w-4" />
                )}
                Run Terraform Plan
              </Button>
            ) : (
              <div className="space-y-3">
                <div
                  className={`flex items-center gap-2 ${
                    planResult.success ? "text-green-500" : "text-red-500"
                  }`}
                >
                  {planResult.success ? (
                    <CheckCircle2 className="h-4 w-4" />
                  ) : (
                    <XCircle className="h-4 w-4" />
                  )}
                  <span className="text-sm font-medium">
                    {planResult.success ? "Plan successful" : "Plan failed"}
                  </span>
                </div>

                {planResult.error && (
                  <div className="p-2 rounded bg-red-500/10 border border-red-500/20 text-xs text-red-400 font-mono whitespace-pre-wrap max-h-[200px] overflow-y-auto">
                    {planResult.error}
                  </div>
                )}

                {planResult.resource_changes && planResult.resource_changes.length > 0 && (
                  <div className="space-y-2">
                    <div className="text-xs font-medium text-muted-foreground">
                      Resource Changes ({planResult.resource_changes.length})
                    </div>
                    <div className="border border-zinc-800 rounded-lg overflow-hidden">
                      <div className="max-h-[200px] overflow-y-auto">
                        {planResult.resource_changes.map((change, i) => (
                          <div
                            key={i}
                            className="flex items-center gap-2 px-3 py-2 text-xs border-b border-zinc-800 last:border-0 hover:bg-zinc-900/50"
                          >
                            <div className="flex items-center gap-1">
                              {change.actions.includes("create") && (
                                <Plus className="h-3 w-3 text-green-500" />
                              )}
                              {change.actions.includes("delete") && (
                                <Minus className="h-3 w-3 text-red-500" />
                              )}
                              {change.actions.includes("update") && (
                                <RefreshCw className="h-3 w-3 text-yellow-500" />
                              )}
                            </div>
                            <span className="font-mono text-muted-foreground truncate" title={change.address}>
                              {change.address}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {planResult.success && (!planResult.resource_changes || planResult.resource_changes.length === 0) && (
                  <div className="text-xs text-muted-foreground">
                    No changes detected. Infrastructure is up to date.
                  </div>
                )}

                <Button
                  onClick={handlePlan}
                  disabled={planning}
                  variant="outline"
                  size="sm"
                  className="w-full"
                >
                  {planning ? (
                    <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                  ) : (
                    <ClipboardList className="mr-2 h-3 w-3" />
                  )}
                  Re-run Plan
                </Button>
              </div>
            )}
          </TabsContent>

          <TabsContent value="cost" className="mt-4">
            {!cost ? (
              <Button
                onClick={handleEstimateCost}
                disabled={estimating}
                className="w-full"
                variant="outline"
              >
                {estimating ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <DollarSign className="mr-2 h-4 w-4" />
                )}
                Estimate Monthly Cost
              </Button>
            ) : (
              <CostBreakdown cost={cost} />
            )}
          </TabsContent>

          <TabsContent value="security" className="mt-4">
            <div className="space-y-3">
              {hasScanned ? (
                <>
                  <SecurityIssuesTable issues={securityIssues} hasScanned={hasScanned} />
                  <Button
                    onClick={handleSecurityScan}
                    disabled={scanning}
                    variant="outline"
                    size="sm"
                    className="w-full"
                  >
                    {scanning ? (
                      <Loader2 className="mr-2 h-3 w-3 animate-spin" />
                    ) : (
                      <Shield className="mr-2 h-3 w-3" />
                    )}
                    Re-scan After Edits
                  </Button>
                </>
              ) : (
                <Button
                  onClick={handleSecurityScan}
                  disabled={scanning}
                  className="w-full"
                  variant="outline"
                >
                  {scanning ? (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  ) : (
                    <Shield className="mr-2 h-4 w-4" />
                  )}
                  Run Security Scan (tfsec + Checkov + Conftest)
                </Button>
              )}
            </div>
          </TabsContent>

          <TabsContent value="export" className="mt-4">
            <div className="grid gap-2">
              <Button onClick={handleDownload} variant="outline" className="w-full">
                <Download className="mr-2 h-4 w-4" />
                Download Files
              </Button>
              <Button variant="outline" className="w-full" disabled>
                <GitBranch className="mr-2 h-4 w-4" />
                Push to Repository
              </Button>
            </div>
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
