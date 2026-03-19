/**
 * Pipeline stage definitions for the UI progress tracker.
 * Maps agent names to display labels, icons, and descriptions.
 */

export type StageStatus = 'pending' | 'running' | 'success' | 'failed' | 'skipped';

export interface PipelineStage {
  id: string;
  agentName: string;
  label: string;
  shortLabel: string;
  description: string;
  icon: string;
}

export const PIPELINE_STAGES: PipelineStage[] = [
  {
    id: 'clarify',
    agentName: 'ClarificationAgent',
    label: 'Clarification',
    shortLabel: 'Clarify',
    description: 'Analyzing prompt completeness and gathering requirements',
    icon: '💬',
  },
  {
    id: 'codegen',
    agentName: 'CodeGenerationAgent',
    label: 'Code Generation',
    shortLabel: 'Code',
    description: 'Generating Terraform infrastructure code',
    icon: '⚙️',
  },
  {
    id: 'validation',
    agentName: 'ValidationAgent',
    label: 'Validate & Plan',
    shortLabel: 'Valid',
    description: 'Running terraform fmt, init, validate, and plan',
    icon: '✓',
  },
  {
    id: 'cost',
    agentName: 'CostEstimationAgent',
    label: 'Cost Estimation',
    shortLabel: 'Cost',
    description: 'Estimating infrastructure costs with Infracost',
    icon: '💰',
  },
];

// Security stages - available for manual scanning from options panel
export const SECURITY_STAGES: PipelineStage[] = [
  {
    id: 'tfsec',
    agentName: 'SecurityAgent',
    label: 'Security (tfsec)',
    shortLabel: 'tfsec',
    description: 'Running tfsec security scanner',
    icon: '🔒',
  },
  {
    id: 'checkov',
    agentName: 'CheckovAgent',
    label: 'Checkov',
    shortLabel: 'Checkov',
    description: 'Running Checkov policy scanner',
    icon: '🛡️',
  },
  {
    id: 'policy',
    agentName: 'PolicyAgent',
    label: 'Policy (OPA)',
    shortLabel: 'Policy',
    description: 'Running custom OPA/Conftest policies',
    icon: '📋',
  },
];

/**
 * Get stage by agent name
 */
export function getStageByAgentName(agentName: string): PipelineStage | undefined {
  return PIPELINE_STAGES.find((stage) => stage.agentName === agentName);
}

/**
 * Get stage index by agent name
 */
export function getStageIndex(agentName: string): number {
  return PIPELINE_STAGES.findIndex((stage) => stage.agentName === agentName);
}

/**
 * Get stage status based on current agent and completion state
 */
export function getStageStatus(
  stage: PipelineStage,
  currentAgent: string | null,
  completedAgents: Set<string>,
  failedAgents: Set<string>,
  skippedAgents: Set<string>
): StageStatus {
  if (failedAgents.has(stage.agentName)) {
    return 'failed';
  }
  if (skippedAgents.has(stage.agentName)) {
    return 'skipped';
  }
  if (completedAgents.has(stage.agentName)) {
    return 'success';
  }
  if (currentAgent === stage.agentName) {
    return 'running';
  }
  return 'pending';
}

/**
 * Get display message for current agent
 */
export function getAgentMessage(agentName: string): string {
  const stage = getStageByAgentName(agentName);
  if (!stage) {
    return `Running ${agentName}...`;
  }
  return stage.description;
}
