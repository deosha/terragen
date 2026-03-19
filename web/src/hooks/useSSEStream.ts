"use client";

import { useEffect, useRef, useState, useCallback } from "react";

export interface LogEntry {
  timestamp: string;
  level: "info" | "success" | "warning" | "error";
  agent?: string;
  message: string;
  details?: string;
}

export interface SSEData {
  status: string;
  current_agent: string | null;
  completed_agents: string[];
  skipped_agents: string[];
  failed_agents: string[];
  files: Record<string, string> | null;
  security_issues: Array<{
    severity: string;
    rule_id: string;
    description: string;
    location?: string;
    file_path?: string;
    line_number?: number;
  }> | null;
  validation_errors: Array<{
    type: string;
    message: string;
    file_path?: string;
    line_number?: number;
  }> | null;
  cost_estimate: {
    monthly?: string;
    yearly?: string;
    breakdown?: Array<{ resource: string; monthly: string }>;
  } | null;
  error: string | null;
  fix_attempt?: number;
  max_fix_attempts?: number;
  logs?: LogEntry[];
}

interface UseSSEStreamOptions {
  onMessage?: (data: SSEData) => void;
  onError?: (error: Event) => void;
  onComplete?: (data: SSEData) => void;
  autoReconnect?: boolean;
  reconnectDelay?: number;
  maxReconnectAttempts?: number;
}

interface UseSSEStreamReturn {
  data: SSEData | null;
  isConnected: boolean;
  isComplete: boolean;
  error: string | null;
  logs: LogEntry[];
  connect: (sessionId: string) => void;
  disconnect: () => void;
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export function useSSEStream(options: UseSSEStreamOptions = {}): UseSSEStreamReturn {
  const {
    onMessage,
    onError,
    onComplete,
    autoReconnect = true,
    reconnectDelay = 2000,
    maxReconnectAttempts = 3,
  } = options;

  const [data, setData] = useState<SSEData | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isComplete, setIsComplete] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([]);

  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const sessionIdRef = useRef<string | null>(null);
  const lastAgentRef = useRef<string | null>(null);
  const lastFixAttemptRef = useRef<number | null>(null);

  const addLog = useCallback((entry: LogEntry) => {
    setLogs((prev) => [...prev, entry]);
  }, []);

  const disconnect = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    setIsConnected(false);
  }, []);

  const connect = useCallback(
    (sessionId: string) => {
      // Close existing connection
      disconnect();

      sessionIdRef.current = sessionId;
      setIsComplete(false);
      setError(null);
      setLogs([]);
      lastAgentRef.current = null;
      lastFixAttemptRef.current = null;

      const token = localStorage.getItem("token");
      if (!token) {
        setError("No authentication token");
        return;
      }

      // Add initial log
      addLog({
        timestamp: new Date().toISOString(),
        level: "info",
        message: "Starting infrastructure generation...",
      });

      const url = `${API_URL}/generate/${sessionId}/stream?token=${token}`;
      const eventSource = new EventSource(url);
      eventSourceRef.current = eventSource;

      eventSource.onopen = () => {
        setIsConnected(true);
        setError(null);
        reconnectAttemptsRef.current = 0;
      };

      eventSource.onmessage = (event) => {
        try {
          const parsedData: SSEData = JSON.parse(event.data);
          setData(parsedData);

          // Generate log entries for agent changes
          if (parsedData.current_agent && parsedData.current_agent !== lastAgentRef.current) {
            // Log completion of previous agent
            if (lastAgentRef.current) {
              addLog({
                timestamp: new Date().toISOString(),
                level: "success",
                agent: lastAgentRef.current,
                message: `${lastAgentRef.current} complete`,
              });
            }

            // Log start of new agent
            addLog({
              timestamp: new Date().toISOString(),
              level: "info",
              agent: parsedData.current_agent,
              message: `Running ${parsedData.current_agent}...`,
            });

            lastAgentRef.current = parsedData.current_agent;
          }

          // Log fix attempts - only when the attempt number changes
          if (parsedData.fix_attempt && parsedData.max_fix_attempts &&
              parsedData.fix_attempt !== lastFixAttemptRef.current) {
            lastFixAttemptRef.current = parsedData.fix_attempt;
            addLog({
              timestamp: new Date().toISOString(),
              level: "warning",
              message: `Fix attempt ${parsedData.fix_attempt}/${parsedData.max_fix_attempts}`,
            });
          }

          // Add any server-side logs
          if (parsedData.logs) {
            parsedData.logs.forEach((log) => {
              addLog(log);
            });
          }

          // Notify callback
          onMessage?.(parsedData);

          // Check for completion
          const isCompleted = parsedData.status === "completed" || parsedData.status === "completed_with_warnings";
          if (isCompleted || parsedData.status === "error") {
            setIsComplete(true);

            // Log completion status
            if (isCompleted) {
              const hasWarnings = parsedData.status === "completed_with_warnings";
              addLog({
                timestamp: new Date().toISOString(),
                level: hasWarnings ? "warning" : "success",
                message: hasWarnings
                  ? `Generation complete with warnings. Generated ${parsedData.files ? Object.keys(parsedData.files).length : 0} files. Review security issues.`
                  : `Generation complete! Generated ${parsedData.files ? Object.keys(parsedData.files).length : 0} files.`,
              });
            } else if (parsedData.error) {
              addLog({
                timestamp: new Date().toISOString(),
                level: "error",
                message: `Generation failed: ${parsedData.error}`,
              });
            }

            onComplete?.(parsedData);
            disconnect();
          }
        } catch (e) {
          console.error("Error parsing SSE data:", e);
        }
      };

      eventSource.onerror = (event) => {
        console.error("SSE error:", event);
        setIsConnected(false);

        if (!isComplete && autoReconnect && reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          addLog({
            timestamp: new Date().toISOString(),
            level: "warning",
            message: `Connection lost. Reconnecting (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`,
          });

          setTimeout(() => {
            if (sessionIdRef.current) {
              connect(sessionIdRef.current);
            }
          }, reconnectDelay);
        } else if (reconnectAttemptsRef.current >= maxReconnectAttempts) {
          setError("Connection lost. Please refresh the page.");
          addLog({
            timestamp: new Date().toISOString(),
            level: "error",
            message: "Connection lost after maximum reconnection attempts.",
          });
          onError?.(event);
        }
      };
    },
    [disconnect, addLog, onMessage, onComplete, onError, autoReconnect, reconnectDelay, maxReconnectAttempts, isComplete]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      disconnect();
    };
  }, [disconnect]);

  return {
    data,
    isConnected,
    isComplete,
    error,
    logs,
    connect,
    disconnect,
  };
}
