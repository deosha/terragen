"use client";

import { motion } from "framer-motion";
import { CheckCircle2, Circle, Loader2, XCircle, MinusCircle } from "lucide-react";
import { PIPELINE_STAGES, StageStatus, getStageByAgentName } from "@/lib/pipelineStages";

interface PipelineProgressProps {
  currentAgent: string | null;
  completedAgents: Set<string>;
  failedAgents: Set<string>;
  skippedAgents: Set<string>;
  fixAttempt?: number;
  maxFixAttempts?: number;
  error?: string | null;
}

export function PipelineProgress({
  currentAgent,
  completedAgents,
  failedAgents,
  skippedAgents,
  fixAttempt,
  maxFixAttempts,
  error,
}: PipelineProgressProps) {
  const getStatus = (agentName: string): StageStatus => {
    // Check completed FIRST - if an agent succeeded after failing, show success
    if (completedAgents.has(agentName)) return "success";
    // Then check if currently running
    if (currentAgent === agentName) return "running";
    // Then check failed/skipped (only if not completed or running)
    if (failedAgents.has(agentName)) return "failed";
    if (skippedAgents.has(agentName)) return "skipped";
    return "pending";
  };

  const currentStage = currentAgent ? getStageByAgentName(currentAgent) : null;

  return (
    <div className="rounded-lg border bg-card p-4">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="font-semibold">Generating Infrastructure</h3>
        {fixAttempt && maxFixAttempts && (
          <motion.span
            initial={{ opacity: 0, scale: 0.9 }}
            animate={{ opacity: 1, scale: 1 }}
            className="rounded-full bg-yellow-500/20 px-3 py-1 text-xs font-medium text-yellow-500"
          >
            Fix Loop: Attempt {fixAttempt}/{maxFixAttempts}
          </motion.span>
        )}
      </div>

      {/* Horizontal Stepper */}
      <div className="relative mb-6">
        {/* Connection Line */}
        <div className="absolute left-0 right-0 top-4 h-0.5 bg-muted" />

        {/* Progress Line */}
        <motion.div
          className="absolute left-0 top-4 h-0.5 bg-primary"
          initial={{ width: "0%" }}
          animate={{
            width: `${calculateProgress(currentAgent, completedAgents, PIPELINE_STAGES)}%`,
          }}
          transition={{ duration: 0.5, ease: "easeInOut" }}
        />

        {/* Stage Indicators */}
        <div className="relative flex justify-between">
          {PIPELINE_STAGES.map((stage, index) => {
            const status = getStatus(stage.agentName);
            return (
              <div key={stage.id} className="flex flex-col items-center">
                <StageIndicator status={status} />
                <span
                  className={`mt-2 text-xs font-medium ${
                    status === "running"
                      ? "text-primary"
                      : status === "success"
                      ? "text-green-500"
                      : status === "failed"
                      ? "text-red-500"
                      : status === "skipped"
                      ? "text-muted-foreground"
                      : "text-muted-foreground"
                  }`}
                >
                  {stage.shortLabel}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Current Stage Description */}
      {currentStage && !error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-md bg-muted/50 p-3"
        >
          <div className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin text-primary" />
            <span className="text-sm">
              <span className="font-medium">{currentStage.label}:</span>{" "}
              <span className="text-muted-foreground">{currentStage.description}</span>
            </span>
          </div>
        </motion.div>
      )}

      {/* Error Display */}
      {error && (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="rounded-md bg-red-500/10 p-3"
        >
          <div className="flex items-center gap-2 text-red-500">
            <XCircle className="h-4 w-4" />
            <span className="text-sm font-medium">Pipeline failed</span>
          </div>
          <p className="mt-1 text-sm text-red-400">{error}</p>
        </motion.div>
      )}
    </div>
  );
}

function StageIndicator({ status }: { status: StageStatus }) {
  switch (status) {
    case "success":
      return (
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          <CheckCircle2 className="h-8 w-8 text-green-500" />
        </motion.div>
      );
    case "running":
      return (
        <motion.div
          animate={{ scale: [1, 1.1, 1] }}
          transition={{ duration: 1.5, repeat: Infinity }}
          className="relative"
        >
          <div className="absolute inset-0 animate-ping rounded-full bg-primary/30" />
          <div className="relative flex h-8 w-8 items-center justify-center rounded-full bg-primary">
            <Loader2 className="h-4 w-4 animate-spin text-primary-foreground" />
          </div>
        </motion.div>
      );
    case "failed":
      return (
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
          transition={{ type: "spring", stiffness: 500, damping: 30 }}
        >
          <XCircle className="h-8 w-8 text-red-500" />
        </motion.div>
      );
    case "skipped":
      return (
        <motion.div
          initial={{ scale: 0.5, opacity: 0 }}
          animate={{ scale: 1, opacity: 1 }}
        >
          <MinusCircle className="h-8 w-8 text-muted-foreground" />
        </motion.div>
      );
    case "pending":
    default:
      return <Circle className="h-8 w-8 text-muted-foreground/50" />;
  }
}

function calculateProgress(
  currentAgent: string | null,
  completedAgents: Set<string>,
  stages: typeof PIPELINE_STAGES
): number {
  if (!currentAgent && completedAgents.size === 0) return 0;

  let completedCount = 0;
  let currentIndex = -1;

  for (let i = 0; i < stages.length; i++) {
    if (completedAgents.has(stages[i].agentName)) {
      completedCount = i + 1;
    }
    if (stages[i].agentName === currentAgent) {
      currentIndex = i;
    }
  }

  // If we have a current agent, show progress up to that point
  const effectiveIndex = Math.max(completedCount, currentIndex >= 0 ? currentIndex : 0);

  // Calculate percentage (give partial credit for current stage)
  const totalStages = stages.length;
  const progress =
    currentIndex >= 0
      ? ((effectiveIndex + 0.5) / totalStages) * 100
      : (effectiveIndex / totalStages) * 100;

  return Math.min(progress, 100);
}
