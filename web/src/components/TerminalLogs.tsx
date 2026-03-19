"use client";

import { useRef, useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, ChevronUp, Copy, Trash2, Check, Terminal } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { LogEntry } from "@/hooks/useSSEStream";

interface TerminalLogsProps {
  logs: LogEntry[];
  title?: string;
  initialCommand?: string;
  maxHeight?: string;
  defaultExpanded?: boolean;
}

export function TerminalLogs({
  logs,
  title = "Logs",
  initialCommand,
  maxHeight = "300px",
  defaultExpanded = true,
}: TerminalLogsProps) {
  const [isExpanded, setIsExpanded] = useState(defaultExpanded);
  const [autoScroll, setAutoScroll] = useState(true);
  const [copied, setCopied] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoScroll]);

  // Detect manual scroll to disable auto-scroll
  const handleScroll = () => {
    if (!scrollRef.current) return;
    const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
    const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
    setAutoScroll(isAtBottom);
  };

  const copyLogs = async () => {
    const logText = logs
      .map((log) => {
        const time = formatTime(log.timestamp);
        const prefix = log.agent ? `[${log.agent}]` : "";
        return `${time} ${prefix} ${log.message}${log.details ? `\n  ${log.details}` : ""}`;
      })
      .join("\n");

    await navigator.clipboard.writeText(logText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const clearLogs = () => {
    // Note: This would need to be handled by parent component
    // For now, this is a visual-only component
  };

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 bg-zinc-900 px-3 py-2">
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="flex items-center gap-2 text-sm font-medium text-zinc-300 hover:text-white transition-colors"
        >
          <Terminal className="h-4 w-4" />
          {title}
          {isExpanded ? (
            <ChevronUp className="h-4 w-4" />
          ) : (
            <ChevronDown className="h-4 w-4" />
          )}
        </button>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={copyLogs}
            className="h-7 px-2 text-zinc-400 hover:text-white hover:bg-zinc-800"
          >
            {copied ? (
              <Check className="h-3 w-3" />
            ) : (
              <Copy className="h-3 w-3" />
            )}
          </Button>
        </div>
      </div>

      {/* Terminal Content */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
          >
            <div
              ref={scrollRef}
              onScroll={handleScroll}
              className="overflow-auto font-mono text-xs leading-relaxed"
              style={{ maxHeight }}
            >
              <div className="p-3 space-y-1">
                {/* Initial command */}
                {initialCommand && (
                  <div className="text-green-400">
                    <span className="text-zinc-500">$ </span>
                    {initialCommand}
                  </div>
                )}

                {/* Log entries */}
                {logs.map((log, index) => (
                  <LogLine key={index} log={log} />
                ))}

                {/* Blinking cursor */}
                {logs.length > 0 && (
                  <div className="flex items-center">
                    <span className="inline-block h-4 w-2 animate-pulse bg-green-400" />
                  </div>
                )}
              </div>
            </div>

            {/* Scroll indicator */}
            {!autoScroll && (
              <div className="border-t border-zinc-800 px-3 py-1.5 bg-zinc-900/50">
                <button
                  onClick={() => {
                    setAutoScroll(true);
                    if (scrollRef.current) {
                      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
                    }
                  }}
                  className="text-xs text-zinc-500 hover:text-zinc-300 transition-colors"
                >
                  Scroll locked. Click to resume auto-scroll
                </button>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

function LogLine({ log }: { log: LogEntry }) {
  const time = formatTime(log.timestamp);

  const getLevelStyles = () => {
    switch (log.level) {
      case "success":
        return { color: "text-green-400", icon: "✓" };
      case "warning":
        return { color: "text-yellow-400", icon: "⚠" };
      case "error":
        return { color: "text-red-400", icon: "✗" };
      case "info":
      default:
        return { color: "text-zinc-300", icon: null };
    }
  };

  const { color, icon } = getLevelStyles();

  return (
    <motion.div
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.15 }}
      className={`flex ${color}`}
    >
      <span className="text-zinc-600 shrink-0">[{time}]</span>
      <span className="mx-1">
        {icon && <span className="mr-1">{icon}</span>}
        {log.agent && (
          <span className="text-cyan-400">{log.agent}: </span>
        )}
        <span className={log.level === "error" ? "text-red-300" : ""}>{log.message}</span>
      </span>
    </motion.div>
  );
}

function formatTime(timestamp: string): string {
  try {
    const date = new Date(timestamp);
    return date.toLocaleTimeString("en-US", {
      hour12: false,
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
    });
  } catch {
    return "--:--:--";
  }
}
