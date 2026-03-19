"use client";

import { useState } from "react";
import { motion } from "framer-motion";
import {
  Check,
  X,
  Edit2,
  Plus,
  Trash2,
  Cloud,
  Network,
  ArrowRight,
  AlertCircle,
  Loader2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { AnalyzeImageResponse } from "@/lib/api";

interface DiagramAnalysisProps {
  analysis: AnalyzeImageResponse;
  onConfirm: (modifiedAnalysis: string) => void;
  onCancel: () => void;
  isGenerating?: boolean;
}

export function DiagramAnalysis({
  analysis,
  onConfirm,
  onCancel,
  isGenerating = false,
}: DiagramAnalysisProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [components, setComponents] = useState(analysis.components);
  const [networking, setNetworking] = useState(analysis.networking || "");
  const [dataFlow, setDataFlow] = useState(analysis.data_flow || "");
  const [additionalReqs, setAdditionalReqs] = useState(
    analysis.additional_requirements || ""
  );
  const [newComponent, setNewComponent] = useState({ name: "", description: "" });

  const addComponent = () => {
    if (newComponent.name.trim()) {
      setComponents([...components, { ...newComponent }]);
      setNewComponent({ name: "", description: "" });
    }
  };

  const removeComponent = (index: number) => {
    setComponents(components.filter((_, i) => i !== index));
  };

  const updateComponent = (index: number, field: "name" | "description", value: string) => {
    const updated = [...components];
    updated[index] = { ...updated[index], [field]: value };
    setComponents(updated);
  };

  const handleConfirm = () => {
    // Rebuild the analysis text with modifications
    let modifiedAnalysis = `## Cloud Provider\n${analysis.cloud_provider?.toUpperCase() || "AWS"}\n\n`;

    modifiedAnalysis += `## Components\n`;
    components.forEach((c) => {
      modifiedAnalysis += `- ${c.name}${c.description ? `: ${c.description}` : ""}\n`;
    });

    if (networking) {
      modifiedAnalysis += `\n## Networking\n${networking}\n`;
    }

    if (dataFlow) {
      modifiedAnalysis += `\n## Data Flow\n${dataFlow}\n`;
    }

    if (additionalReqs) {
      modifiedAnalysis += `\n## Additional Requirements\n${additionalReqs}\n`;
    }

    onConfirm(modifiedAnalysis);
  };

  const providerColors: Record<string, string> = {
    aws: "text-orange-500",
    gcp: "text-blue-500",
    azure: "text-cyan-500",
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="rounded-lg border border-zinc-700 bg-zinc-900 overflow-hidden"
    >
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-700 bg-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <Cloud className={`h-5 w-5 ${providerColors[analysis.cloud_provider || "aws"]}`} />
          <h3 className="font-medium">Detected Architecture</h3>
          <span className="rounded bg-zinc-700 px-2 py-0.5 text-xs uppercase">
            {analysis.cloud_provider || "aws"}
          </span>
        </div>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => setIsEditing(!isEditing)}
          className="h-8 text-xs"
        >
          <Edit2 className="mr-1 h-3 w-3" />
          {isEditing ? "Done Editing" : "Edit"}
        </Button>
      </div>

      {/* Content */}
      <div className="p-4 space-y-4">
        {/* Components */}
        <div>
          <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
            <span className="rounded-full bg-primary/20 p-1">
              <Check className="h-3 w-3 text-primary" />
            </span>
            Components ({components.length})
          </h4>
          <div className="space-y-2">
            {components.map((component, index) => (
              <div
                key={index}
                className="flex items-start gap-2 rounded-md bg-zinc-800 p-2"
              >
                {isEditing ? (
                  <>
                    <Input
                      value={component.name}
                      onChange={(e) => updateComponent(index, "name", e.target.value)}
                      className="h-8 flex-1 bg-zinc-900 text-sm"
                      placeholder="Component name"
                    />
                    <Input
                      value={component.description}
                      onChange={(e) => updateComponent(index, "description", e.target.value)}
                      className="h-8 flex-[2] bg-zinc-900 text-sm"
                      placeholder="Description"
                    />
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => removeComponent(index)}
                      className="h-8 w-8 p-0 text-red-400 hover:text-red-300"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </>
                ) : (
                  <div className="flex-1">
                    <span className="font-medium text-sm">{component.name}</span>
                    {component.description && (
                      <span className="text-sm text-zinc-400 ml-2">
                        - {component.description}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}

            {/* Add new component */}
            {isEditing && (
              <div className="flex items-center gap-2 rounded-md border border-dashed border-zinc-600 p-2">
                <Input
                  value={newComponent.name}
                  onChange={(e) => setNewComponent({ ...newComponent, name: e.target.value })}
                  className="h-8 flex-1 bg-zinc-900 text-sm"
                  placeholder="New component name"
                />
                <Input
                  value={newComponent.description}
                  onChange={(e) => setNewComponent({ ...newComponent, description: e.target.value })}
                  className="h-8 flex-[2] bg-zinc-900 text-sm"
                  placeholder="Description (optional)"
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={addComponent}
                  disabled={!newComponent.name.trim()}
                  className="h-8 w-8 p-0"
                >
                  <Plus className="h-4 w-4" />
                </Button>
              </div>
            )}
          </div>
        </div>

        {/* Networking */}
        {(networking || isEditing) && (
          <div>
            <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
              <span className="rounded-full bg-blue-500/20 p-1">
                <Network className="h-3 w-3 text-blue-400" />
              </span>
              Networking
            </h4>
            {isEditing ? (
              <Textarea
                value={networking}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setNetworking(e.target.value)}
                className="min-h-[80px] bg-zinc-800 text-sm"
                placeholder="VPCs, subnets, security groups, load balancers..."
              />
            ) : (
              <p className="text-sm text-zinc-300 whitespace-pre-wrap bg-zinc-800 rounded-md p-2">
                {networking}
              </p>
            )}
          </div>
        )}

        {/* Data Flow */}
        {(dataFlow || isEditing) && (
          <div>
            <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
              <span className="rounded-full bg-green-500/20 p-1">
                <ArrowRight className="h-3 w-3 text-green-400" />
              </span>
              Data Flow
            </h4>
            {isEditing ? (
              <Textarea
                value={dataFlow}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setDataFlow(e.target.value)}
                className="min-h-[80px] bg-zinc-800 text-sm"
                placeholder="How data flows between components..."
              />
            ) : (
              <p className="text-sm text-zinc-300 whitespace-pre-wrap bg-zinc-800 rounded-md p-2">
                {dataFlow}
              </p>
            )}
          </div>
        )}

        {/* Additional Requirements */}
        {(additionalReqs || isEditing) && (
          <div>
            <h4 className="text-sm font-medium text-zinc-400 mb-2 flex items-center gap-2">
              <span className="rounded-full bg-yellow-500/20 p-1">
                <AlertCircle className="h-3 w-3 text-yellow-400" />
              </span>
              Additional Requirements
            </h4>
            {isEditing ? (
              <Textarea
                value={additionalReqs}
                onChange={(e: React.ChangeEvent<HTMLTextAreaElement>) => setAdditionalReqs(e.target.value)}
                className="min-h-[80px] bg-zinc-800 text-sm"
                placeholder="Any other infrastructure requirements..."
              />
            ) : (
              <p className="text-sm text-zinc-300 whitespace-pre-wrap bg-zinc-800 rounded-md p-2">
                {additionalReqs}
              </p>
            )}
          </div>
        )}
      </div>

      {/* Actions */}
      <div className="flex items-center justify-between border-t border-zinc-700 bg-zinc-800/50 px-4 py-3">
        <p className="text-xs text-zinc-400">
          Review the detected components and modify if needed before generating.
        </p>
        <div className="flex items-center gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={onCancel}
            disabled={isGenerating}
          >
            <X className="mr-1 h-4 w-4" />
            Cancel
          </Button>
          <Button
            size="sm"
            onClick={handleConfirm}
            disabled={isGenerating}
          >
            {isGenerating ? (
              <>
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Generating...
              </>
            ) : (
              <>
                <Check className="mr-1 h-4 w-4" />
                Confirm & Generate
              </>
            )}
          </Button>
        </div>
      </div>
    </motion.div>
  );
}
