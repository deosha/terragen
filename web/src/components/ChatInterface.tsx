"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Wand2, MessageSquare, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OptionsPanel } from "./OptionsPanel";
import { CodeEditor } from "./CodeEditor";
import { PipelineProgress } from "./PipelineProgress";
import { TerminalLogs } from "./TerminalLogs";
import { DiagramAnalysis } from "./DiagramAnalysis";
import { InfraBuilder, GenerateParams, ImageGenerateParams } from "./InfraBuilder";
import { api, GenerateResponse, AnalyzeImageResponse } from "@/lib/api";
import { useSSEStream, SSEData } from "@/hooks/useSSEStream";
import { PIPELINE_STAGES } from "@/lib/pipelineStages";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  files?: Record<string, string>;
  options?: {
    showOptions: boolean;
    validation?: { valid: boolean; errors: string[] };
    cost?: { monthly_cost: string };
    security?: { issues: Array<{ severity: string; description: string }> };
  };
}

type Tab = "chat" | "builder";

// localStorage keys
const STORAGE_KEYS = {
  SESSION_ID: 'terragen_session_id',
  MESSAGES: 'terragen_messages',
  FILES: 'terragen_files',
};

export function ChatInterface() {
  // Initialize state from localStorage
  const [messages, setMessages] = useState<Message[]>(() => {
    if (typeof window !== 'undefined') {
      const saved = localStorage.getItem(STORAGE_KEYS.MESSAGES);
      return saved ? JSON.parse(saved) : [];
    }
    return [];
  });
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [currentSession, setCurrentSession] = useState<string | null>(() => {
    if (typeof window !== 'undefined') {
      return localStorage.getItem(STORAGE_KEYS.SESSION_ID);
    }
    return null;
  });
  const [generatedFiles, setGeneratedFiles] = useState<Record<string, string>>(
    () => {
      if (typeof window !== 'undefined') {
        const saved = localStorage.getItem(STORAGE_KEYS.FILES);
        return saved ? JSON.parse(saved) : {};
      }
      return {};
    }
  );
  const [showOptions, setShowOptions] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("chat");
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Persist to localStorage when state changes
  useEffect(() => {
    if (currentSession) {
      localStorage.setItem(STORAGE_KEYS.SESSION_ID, currentSession);
    }
  }, [currentSession]);

  useEffect(() => {
    if (messages.length > 0) {
      localStorage.setItem(STORAGE_KEYS.MESSAGES, JSON.stringify(messages));
    }
  }, [messages]);

  useEffect(() => {
    if (Object.keys(generatedFiles).length > 0) {
      localStorage.setItem(STORAGE_KEYS.FILES, JSON.stringify(generatedFiles));
    }
  }, [generatedFiles]);

  // Pipeline progress tracking
  const [currentAgent, setCurrentAgent] = useState<string | null>(null);
  const [completedAgents, setCompletedAgents] = useState<Set<string>>(new Set());
  const [failedAgents, setFailedAgents] = useState<Set<string>>(new Set());
  const [skippedAgents, setSkippedAgents] = useState<Set<string>>(new Set());
  const [fixAttempt, setFixAttempt] = useState<number | undefined>();
  const [maxFixAttempts, setMaxFixAttempts] = useState<number | undefined>();

  // Security issues and cost from generation
  // Initialize to undefined to distinguish "no scan run" from "scan run with 0 issues"
  const [securityIssues, setSecurityIssues] = useState<Array<{
    severity: string;
    rule_id: string;
    description: string;
    file_path?: string;
    line_number?: number;
    scanner?: string;
  }> | undefined>(undefined);
  const [costEstimate, setCostEstimate] = useState<{
    monthly_cost: string;
    breakdown?: Array<{ name: string; monthly_cost: string }>;
  } | null>(null);
  const [pipelineError, setPipelineError] = useState<string | null>(null);
  const [userPrompt, setUserPrompt] = useState<string>("");

  // Diagram analysis state
  const [pendingAnalysis, setPendingAnalysis] = useState<{
    analysis: AnalyzeImageResponse;
    imageData: string;
    provider: string;
  } | null>(null);
  const [isAnalyzing, setIsAnalyzing] = useState(false);

  // SSE streaming hook
  const {
    data: sseData,
    isConnected,
    isComplete,
    error: sseError,
    logs,
    connect: connectSSE,
    disconnect: disconnectSSE,
  } = useSSEStream({
    onMessage: useCallback((data: SSEData) => {
      // Update current agent
      setCurrentAgent(data.current_agent);

      // Update agent statuses from server
      if (data.completed_agents) {
        setCompletedAgents(new Set(data.completed_agents));
      }
      if (data.skipped_agents) {
        setSkippedAgents(new Set(data.skipped_agents));
      }
      if (data.failed_agents) {
        setFailedAgents(new Set(data.failed_agents));
      }

      // Update fix attempt tracking
      if (data.fix_attempt !== undefined) {
        setFixAttempt(data.fix_attempt);
      }
      if (data.max_fix_attempts !== undefined) {
        setMaxFixAttempts(data.max_fix_attempts);
      }

      // Update files if available
      if (data.files) {
        setGeneratedFiles(data.files);
      }

      // Update security issues
      if (data.security_issues) {
        setSecurityIssues(data.security_issues);
      }

      // Update cost estimate
      if (data.cost_estimate) {
        setCostEstimate({
          monthly_cost: data.cost_estimate.monthly || "$0.00",
          breakdown: data.cost_estimate.breakdown?.map((b: { resource: string; monthly: string }) => ({
            name: b.resource,
            monthly_cost: b.monthly,
          })),
        });
      }
    }, []),
    onComplete: useCallback((data: SSEData) => {
      setCurrentAgent(null);

      // Final update of agent statuses
      if (data.completed_agents) {
        setCompletedAgents(new Set(data.completed_agents));
      }
      if (data.skipped_agents) {
        setSkippedAgents(new Set(data.skipped_agents));
      }
      if (data.failed_agents) {
        setFailedAgents(new Set(data.failed_agents));
      }

      // Final update of security issues
      if (data.security_issues) {
        setSecurityIssues(data.security_issues);
      }

      // Final update of cost estimate
      if (data.cost_estimate) {
        setCostEstimate({
          monthly_cost: data.cost_estimate.monthly || "$0.00",
          breakdown: data.cost_estimate.breakdown?.map((b: { resource: string; monthly: string }) => ({
            name: b.resource,
            monthly_cost: b.monthly,
          })),
        });
      }

      if (data.status === "error" && data.error) {
        setPipelineError(data.error);
      }
    }, []),
  });

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, logs]);

  // Reset pipeline state
  const resetPipelineState = () => {
    setCurrentAgent(null);
    setCompletedAgents(new Set());
    setFailedAgents(new Set());
    setSkippedAgents(new Set());
    setFixAttempt(undefined);
    setMaxFixAttempts(undefined);
    setPipelineError(null);
    setSecurityIssues(undefined);  // Reset to undefined to indicate no scan run
    setCostEstimate(null);
  };

  // Clear chat and start fresh
  const clearChat = () => {
    setMessages([]);
    setCurrentSession(null);
    setGeneratedFiles({});
    resetPipelineState();
    localStorage.removeItem(STORAGE_KEYS.SESSION_ID);
    localStorage.removeItem(STORAGE_KEYS.MESSAGES);
    localStorage.removeItem(STORAGE_KEYS.FILES);
  };

  const handleGenerate = async (input: string | GenerateParams) => {
    const isParams = typeof input !== "string";
    const prompt = isParams ? input.prompt : input;
    const provider = isParams ? input.provider : "aws";
    const backend = isParams ? input.backend : undefined;
    const backendConfig = isParams ? input.backendConfig : undefined;
    const clarifications = isParams ? input.clarifications : undefined;

    if (!prompt.trim() || loading) return;

    // Switch to chat tab when generating
    setActiveTab("chat");
    setUserPrompt(prompt);

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: prompt,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);
    resetPipelineState();

    try {
      // Start generation
      const response = await api.generate({
        prompt,
        provider,
        backend,
        backendConfig,
        clarifications,
      });

      setCurrentSession(response.session_id);

      // Add assistant message with loading state
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Generating your infrastructure...",
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Connect to SSE stream for real-time updates
      connectSSE(response.session_id);

      // Also poll for final status as fallback (SSE might disconnect)
      let result: GenerateResponse;
      let pollCount = 0;
      const maxPolls = 300; // 10 minutes max

      do {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        result = await api.getGenerateStatus(response.session_id);
        pollCount++;

        // Update from poll if SSE isn't providing updates
        if (result.files && !sseData?.files) {
          setGeneratedFiles(result.files);
        }
      } while (
        (result.status === "pending" || result.status === "running") &&
        pollCount < maxPolls
      );

      // Disconnect SSE
      disconnectSSE();

      const isCompleted = result.status === "completed" || result.status === "completed_with_warnings";
      if (isCompleted && result.files) {
        setGeneratedFiles(result.files);
        setShowOptions(true);

        // Mark all agents as completed
        const allAgentNames = PIPELINE_STAGES.map((s) => s.agentName);
        setCompletedAgents(new Set(allAgentNames));
        setCurrentAgent(null);

        // Different message for warnings vs clean completion
        const hasWarnings = result.status === "completed_with_warnings";
        const message = hasWarnings
          ? "I've generated your Terraform configuration, but there are **security issues** that could not be automatically fixed. Please review the Security tab and address these issues before deploying."
          : "I've generated your Terraform configuration. Review the code below and use the options to validate or scan for security issues.";

        // Update assistant message
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: message,
                  files: result.files,
                  options: { showOptions: true },
                }
              : msg
          )
        );
      } else if (result.status === "error") {
        // Get error message from various sources
        const errorMsg = result.error
          || (result.pipeline_summary as Record<string, unknown>)?.failure_reason as string
          || "Generation failed";

        setPipelineError(errorMsg);

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: `Sorry, there was an error: ${errorMsg}`,
                }
              : msg
          )
        );
      }
    } catch (error) {
      console.error("Generation error:", error);
      disconnectSSE();
      setPipelineError(error instanceof Error ? error.message : "Unknown error");
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: "Sorry, there was an error. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    await handleGenerate(input);
  };

  // Step 1: Analyze the diagram
  const handleAnalyzeImage = async (params: { imageData: string; additionalContext: string; provider: string }) => {
    if (isAnalyzing || loading) return;

    // Switch to chat tab
    setActiveTab("chat");

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: `Analyze architecture diagram${params.additionalContext ? `: ${params.additionalContext}` : ""}`,
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsAnalyzing(true);

    try {
      // Analyze the diagram
      const analysisResult = await api.analyzeImage({
        image_data: params.imageData,
        additional_context: params.additionalContext || undefined,
      });

      // Store pending analysis for confirmation
      setPendingAnalysis({
        analysis: analysisResult,
        imageData: params.imageData,
        provider: analysisResult.cloud_provider || params.provider,
      });

      // Add assistant message prompting for confirmation
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I've analyzed your architecture diagram. Please review the detected components and confirm or modify before I generate the Terraform code.",
        },
      ]);
    } catch (error) {
      console.error("Image analysis error:", error);
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: `Sorry, there was an error analyzing your diagram: ${error instanceof Error ? error.message : "Unknown error"}`,
        },
      ]);
    } finally {
      setIsAnalyzing(false);
    }
  };

  // Step 2: Generate with confirmed analysis
  const handleConfirmAndGenerate = async (confirmedAnalysis: string) => {
    if (!pendingAnalysis || loading) return;

    setLoading(true);
    resetPipelineState();
    setUserPrompt(`[Architecture diagram - confirmed]`);

    try {
      // Start image-based generation with confirmed analysis
      const response = await api.generateFromImage({
        image_data: pendingAnalysis.imageData,
        provider: pendingAnalysis.provider,
        confirmed_analysis: confirmedAnalysis,
      });

      setCurrentSession(response.session_id);
      setPendingAnalysis(null);  // Clear pending analysis

      // Add assistant message with loading state
      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Generating your Terraform configuration based on the confirmed requirements...",
      };
      setMessages((prev) => [...prev, assistantMessage]);

      // Connect to SSE stream for real-time updates
      connectSSE(response.session_id);

      // Poll for final status as fallback
      let result: GenerateResponse;
      let pollCount = 0;
      const maxPolls = 300; // 10 minutes max

      do {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        result = await api.getGenerateStatus(response.session_id);
        pollCount++;

        // Update from poll if SSE isn't providing updates
        if (result.files && !sseData?.files) {
          setGeneratedFiles(result.files);
        }
      } while (
        (result.status === "pending" || result.status === "running") &&
        pollCount < maxPolls
      );

      // Disconnect SSE
      disconnectSSE();

      const isCompleted = result.status === "completed" || result.status === "completed_with_warnings";
      if (isCompleted && result.files) {
        setGeneratedFiles(result.files);
        setShowOptions(true);

        // Mark all agents as completed
        const allAgentNames = PIPELINE_STAGES.map((s) => s.agentName);
        setCompletedAgents(new Set(allAgentNames));
        setCurrentAgent(null);

        // Different message for warnings vs clean completion
        const hasWarnings = result.status === "completed_with_warnings";
        const message = hasWarnings
          ? "I've generated your Terraform configuration, but there are **security issues** that could not be automatically fixed. Please review the Security tab."
          : "I've generated your Terraform configuration based on your architecture diagram. Review the code below.";

        // Update assistant message
        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: message,
                  files: result.files,
                  options: { showOptions: true },
                }
              : msg
          )
        );
      } else if (result.status === "error") {
        // Get error message from various sources
        const errorMsg = result.error
          || (result.pipeline_summary as Record<string, unknown>)?.failure_reason as string
          || "Generation failed";

        setPipelineError(errorMsg);

        setMessages((prev) =>
          prev.map((msg) =>
            msg.id === assistantMessage.id
              ? {
                  ...msg,
                  content: `Sorry, there was an error: ${errorMsg}`,
                }
              : msg
          )
        );
      }
    } catch (error) {
      console.error("Image generation error:", error);
      disconnectSSE();
      setPipelineError(error instanceof Error ? error.message : "Unknown error");
      setMessages((prev) => [
        ...prev,
        {
          id: Date.now().toString(),
          role: "assistant",
          content: "Sorry, there was an error generating your infrastructure. Please try again.",
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  // Cancel pending analysis
  const handleCancelAnalysis = () => {
    setPendingAnalysis(null);
    setMessages((prev) => [
      ...prev,
      {
        id: Date.now().toString(),
        role: "assistant",
        content: "Generation cancelled. Feel free to upload a different diagram or modify your requirements.",
      },
    ]);
  };

  // Legacy handler that combines analyze + generate (for direct generation without confirmation)
  const handleGenerateFromImage = async (params: ImageGenerateParams) => {
    // If confirmed analysis is provided, generate directly
    if (params.confirmedAnalysis) {
      setPendingAnalysis({
        analysis: { analysis: params.confirmedAnalysis, components: [] },
        imageData: params.imageData,
        provider: params.provider,
      });
      await handleConfirmAndGenerate(params.confirmedAnalysis);
      return;
    }

    // Otherwise, analyze first
    await handleAnalyzeImage({
      imageData: params.imageData,
      additionalContext: params.additionalContext,
      provider: params.provider,
    });
  };

  const handleOptionComplete = (type: string, result: unknown) => {
    console.log("Option completed:", type, result);
  };

  const handleFileSave = async (files: Record<string, string>) => {
    if (!currentSession) return;

    try {
      await api.updateSessionFiles(currentSession, files);
      setGeneratedFiles(files);
    } catch (error) {
      console.error("Failed to save files:", error);
      throw error;
    }
  };

  const handleValidate = async (files: Record<string, string>) => {
    try {
      const result = await api.validate(files);
      if (!result.valid) {
        console.log("Validation errors:", result.errors);
      }
    } catch (error) {
      console.error("Validation failed:", error);
    }
  };

  const handleSecurityScan = async (files: Record<string, string>) => {
    try {
      const result = await api.securityScan(files);
      console.log("Security scan results:", result);
    } catch (error) {
      console.error("Security scan failed:", error);
    }
  };

  return (
    <div className="flex h-[calc(100vh-3.5rem)] flex-col">
      {/* Tabs */}
      <div className="border-b bg-background">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <div className="flex">
            <button
              onClick={() => setActiveTab("chat")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === "chat"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <MessageSquare className="h-4 w-4" />
              Chat
            </button>
            <button
              onClick={() => setActiveTab("builder")}
              className={`flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors ${
                activeTab === "builder"
                  ? "border-primary text-primary"
                  : "border-transparent text-muted-foreground hover:text-foreground"
              }`}
            >
              <Wand2 className="h-4 w-4" />
              Prompt Builder
            </button>
          </div>
          {messages.length > 0 && (
            <button
              onClick={clearChat}
              className="flex items-center gap-1 px-3 py-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
              title="Clear chat and start fresh"
            >
              <Trash2 className="h-3 w-3" />
              Clear
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-4xl">
          {activeTab === "builder" ? (
            <InfraBuilder
              onGenerate={handleGenerate}
              onGenerateFromImage={handleGenerateFromImage}
              isLoading={loading || isAnalyzing}
            />
          ) : (
            <div className="space-y-4">
              {messages.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-16 text-center">
                  <h2 className="text-2xl font-semibold">
                    What infrastructure do you want to create?
                  </h2>
                  <p className="mt-2 max-w-md text-muted-foreground">
                    Describe your infrastructure in plain English, or use the Prompt Builder for a guided experience.
                  </p>

                  {/* Quick Examples */}
                  <div className="mt-8 grid gap-2 sm:grid-cols-2">
                    {[
                      "S3 bucket with versioning and encryption",
                      "EKS cluster with 3 node groups",
                      "Serverless API with Lambda and DynamoDB",
                      "VPC with public and private subnets",
                    ].map((example, i) => (
                      <button
                        key={i}
                        onClick={() => setInput(example)}
                        className="rounded-lg border border-border bg-card px-4 py-3 text-left text-sm transition-colors hover:bg-accent"
                      >
                        &quot;{example}&quot;
                      </button>
                    ))}
                  </div>

                  {/* Prompt Builder CTA */}
                  <div className="mt-8 rounded-lg border border-dashed border-primary/50 bg-primary/5 p-6">
                    <div className="flex items-center gap-3">
                      <div className="rounded-full bg-primary/10 p-3">
                        <Wand2 className="h-6 w-6 text-primary" />
                      </div>
                      <div className="text-left">
                        <h3 className="font-medium">Try the Prompt Builder</h3>
                        <p className="text-sm text-muted-foreground">
                          Select services visually, choose production options, and build your infrastructure step by step.
                        </p>
                      </div>
                    </div>
                    <Button
                      onClick={() => setActiveTab("builder")}
                      className="mt-4 w-full"
                      variant="outline"
                    >
                      <Wand2 className="mr-2 h-4 w-4" />
                      Open Prompt Builder
                    </Button>
                  </div>
                </div>
              ) : (
                <>
                  {messages.map((message) => (
                    <div key={message.id} className="space-y-4">
                      {/* Message bubble */}
                      <div
                        className={`flex ${
                          message.role === "user" ? "justify-end" : "justify-start"
                        }`}
                      >
                        <div
                          className={`max-w-[80%] rounded-lg px-4 py-2 ${
                            message.role === "user"
                              ? "bg-primary text-primary-foreground"
                              : "bg-muted"
                          }`}
                        >
                          <p>{message.content}</p>
                        </div>
                      </div>

                      {/* Code Editor - OUTSIDE message bubble for full width */}
                      {message.files && Object.keys(message.files).length > 0 && (
                        <div className="w-full">
                          <CodeEditor
                            files={message.files}
                            onSave={handleFileSave}
                          />
                        </div>
                      )}

                      {/* Options Panel - OUTSIDE message bubble */}
                      {message.options?.showOptions && (
                        <div className="w-full">
                          <OptionsPanel
                            files={generatedFiles}
                            onComplete={handleOptionComplete}
                            initialSecurityIssues={securityIssues}
                            initialCostEstimate={costEstimate || undefined}
                          />
                        </div>
                      )}
                    </div>
                  ))}

                  {/* Analyzing Diagram Indicator */}
                  {isAnalyzing && (
                    <div className="rounded-lg border border-zinc-700 bg-zinc-900 p-6">
                      <div className="flex items-center gap-4">
                        <div className="relative">
                          <div className="h-12 w-12 rounded-full border-4 border-zinc-700 border-t-primary animate-spin" />
                        </div>
                        <div>
                          <h3 className="font-medium">Analyzing Architecture Diagram</h3>
                          <p className="text-sm text-zinc-400">
                            Extracting components, networking, and infrastructure requirements...
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Diagram Analysis Confirmation */}
                  {pendingAnalysis && !loading && !isAnalyzing && (
                    <DiagramAnalysis
                      analysis={pendingAnalysis.analysis}
                      onConfirm={handleConfirmAndGenerate}
                      onCancel={handleCancelAnalysis}
                      isGenerating={loading}
                    />
                  )}

                  {/* Pipeline Progress - show during loading */}
                  {loading && (
                    <PipelineProgress
                      currentAgent={currentAgent}
                      completedAgents={completedAgents}
                      failedAgents={failedAgents}
                      skippedAgents={skippedAgents}
                      fixAttempt={fixAttempt}
                      maxFixAttempts={maxFixAttempts}
                      error={pipelineError}
                    />
                  )}

                  {/* Terminal Logs - persist after completion if there are logs */}
                  {(loading || logs.length > 0) && (
                    <TerminalLogs
                      logs={logs}
                      title={loading ? "Logs" : "Generation Logs"}
                      initialCommand={`terragen generate "${userPrompt.slice(0, 50)}${userPrompt.length > 50 ? '...' : ''}"`}
                      maxHeight="250px"
                      defaultExpanded={loading}
                    />
                  )}
                </>
              )}

              <div ref={messagesEndRef} />
            </div>
          )}
        </div>
      </div>

      {/* Input - only show in chat tab */}
      {activeTab === "chat" && (
        <div className="border-t bg-background p-4">
          <form
            onSubmit={handleSubmit}
            className="mx-auto flex max-w-4xl items-center gap-2"
          >
            <Input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Describe your infrastructure..."
              className="flex-1"
              disabled={loading}
            />

            <Button
              type="button"
              variant="outline"
              size="icon"
              onClick={() => setActiveTab("builder")}
              title="Open Prompt Builder"
            >
              <Wand2 className="h-4 w-4" />
            </Button>

            <Button type="submit" size="icon" disabled={loading || !input.trim()}>
              {loading ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </form>
        </div>
      )}
    </div>
  );
}
