"use client";

import { useState, useMemo } from "react";
import {
  X,
  Plus,
  Search,
  Cpu,
  Database,
  HardDrive,
  Network,
  Shield,
  Radio,
  BarChart3,
  Brain,
  Activity,
  GitBranch,
  Globe,
  Zap,
  Boxes,
  Layers,
  Check,
  ChevronDown,
  Workflow,
  Image as ImageIcon,
  Wand2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ImageUpload } from "./ImageUpload";
import servicesConfig from "@/config/services.json";
import patternsConfig from "@/config/patterns.json";

type Provider = "aws" | "gcp" | "azure";

interface Service {
  id: string;
  name: string;
  category: string;
  description: string;
}

interface Pattern {
  id: string;
  name: string;
  description: string;
  icon: string;
  category: string;
  services: Record<string, string[]>;
}

interface ProductionOption {
  id: string;
  name: string;
  description: string;
  default: boolean;
}

const categoryIcons: Record<string, React.ReactNode> = {
  compute: <Cpu className="h-4 w-4" />,
  containers: <Boxes className="h-4 w-4" />,
  serverless: <Zap className="h-4 w-4" />,
  database: <Database className="h-4 w-4" />,
  storage: <HardDrive className="h-4 w-4" />,
  networking: <Network className="h-4 w-4" />,
  security: <Shield className="h-4 w-4" />,
  messaging: <Radio className="h-4 w-4" />,
  analytics: <BarChart3 className="h-4 w-4" />,
  ml: <Brain className="h-4 w-4" />,
  monitoring: <Activity className="h-4 w-4" />,
  devops: <GitBranch className="h-4 w-4" />,
  cdn: <Globe className="h-4 w-4" />,
};

const patternIcons: Record<string, React.ReactNode> = {
  zap: <Zap className="h-5 w-5" />,
  boxes: <Boxes className="h-5 w-5" />,
  layers: <Layers className="h-5 w-5" />,
  database: <Database className="h-5 w-5" />,
  "bar-chart": <BarChart3 className="h-5 w-5" />,
  brain: <Brain className="h-5 w-5" />,
  radio: <Radio className="h-5 w-5" />,
  "git-branch": <GitBranch className="h-5 w-5" />,
  shield: <Shield className="h-5 w-5" />,
  globe: <Globe className="h-5 w-5" />,
  activity: <Activity className="h-5 w-5" />,
  workflow: <Workflow className="h-5 w-5" />,
  search: <Search className="h-5 w-5" />,
};

export type Backend = "local" | "s3" | "gcs" | "azurerm" | "remote";

export interface BackendConfig {
  type: Backend;
  // S3 backend
  bucket?: string;
  key?: string;
  region?: string;
  dynamodb_table?: string;
  // GCS backend
  prefix?: string;
  // Azure backend
  resource_group_name?: string;
  storage_account_name?: string;
  container_name?: string;
  // Terraform Cloud
  organization?: string;
  workspace?: string;
}

export interface GenerateParams {
  prompt: string;
  provider: string;
  services: string[];
  backend: Backend;
  backendConfig?: BackendConfig;
  clarifications: Record<string, boolean | string>;
}

export interface ImageAnalyzeParams {
  imageData: string;
  additionalContext: string;
}

export interface ImageGenerateParams {
  imageData: string;
  additionalContext: string;
  provider: string;
  confirmedAnalysis?: string;  // Pre-confirmed analysis
}

interface InfraBuilderProps {
  onGenerate: (params: GenerateParams) => void;
  onGenerateFromImage?: (params: ImageGenerateParams) => Promise<void>;
  isLoading?: boolean;
}

type BuildMode = "services" | "diagram";

export function InfraBuilder({ onGenerate, onGenerateFromImage, isLoading = false }: InfraBuilderProps) {
  const [buildMode, setBuildMode] = useState<BuildMode>("services");
  const [provider, setProvider] = useState<Provider>("aws");
  const [selectedServices, setSelectedServices] = useState<string[]>([]);
  const [selectedPattern, setSelectedPattern] = useState<string | null>(null);
  const [backend, setBackend] = useState<Backend>("local");
  const [backendConfig, setBackendConfig] = useState<BackendConfig>({ type: "local" });
  const [productionOptions, setProductionOptions] = useState<Record<string, boolean>>(() => {
    const initial: Record<string, boolean> = {};
    patternsConfig.productionOptions.forEach((opt) => {
      initial[opt.id] = opt.default;
    });
    return initial;
  });
  const [showServicePicker, setShowServicePicker] = useState(false);
  const [serviceSearch, setServiceSearch] = useState("");
  const [expandedCategory, setExpandedCategory] = useState<string | null>(null);

  const services = servicesConfig.services[provider] as Service[];
  const patterns = patternsConfig.patterns as Pattern[];
  const prodOptions = patternsConfig.productionOptions as ProductionOption[];
  const categories = servicesConfig.categories;

  const serviceMap = useMemo(() => {
    const map: Record<string, Service> = {};
    services.forEach((s) => {
      map[s.id] = s;
    });
    return map;
  }, [services]);

  const filteredServices = useMemo(() => {
    if (!serviceSearch) return services;
    const search = serviceSearch.toLowerCase();
    return services.filter(
      (s) =>
        s.name.toLowerCase().includes(search) ||
        s.description.toLowerCase().includes(search)
    );
  }, [services, serviceSearch]);

  const groupedServices = useMemo(() => {
    const groups: Record<string, Service[]> = {};
    filteredServices.forEach((s) => {
      if (!groups[s.category]) groups[s.category] = [];
      groups[s.category].push(s);
    });
    return groups;
  }, [filteredServices]);

  const handlePatternSelect = (patternId: string) => {
    if (selectedPattern === patternId) {
      setSelectedPattern(null);
      setSelectedServices([]);
    } else {
      setSelectedPattern(patternId);
      const pattern = patterns.find((p) => p.id === patternId);
      if (pattern) {
        setSelectedServices(pattern.services[provider] || []);
      }
    }
  };

  const handleProviderChange = (newProvider: Provider) => {
    setProvider(newProvider);
    // Update services if a pattern is selected
    if (selectedPattern) {
      const pattern = patterns.find((p) => p.id === selectedPattern);
      if (pattern) {
        setSelectedServices(pattern.services[newProvider] || []);
      }
    } else {
      setSelectedServices([]);
    }
  };

  const addService = (serviceId: string) => {
    if (!selectedServices.includes(serviceId)) {
      setSelectedServices([...selectedServices, serviceId]);
      setSelectedPattern(null); // Clear pattern selection when manually editing
    }
    setShowServicePicker(false);
    setServiceSearch("");
  };

  const removeService = (serviceId: string) => {
    setSelectedServices(selectedServices.filter((s) => s !== serviceId));
    setSelectedPattern(null);
  };

  const toggleProductionOption = (optionId: string) => {
    setProductionOptions((prev) => ({
      ...prev,
      [optionId]: !prev[optionId],
    }));
  };

  const handleBackendChange = (newBackend: Backend) => {
    setBackend(newBackend);
    setBackendConfig({ type: newBackend });
  };

  const updateBackendConfig = (key: keyof BackendConfig, value: string) => {
    setBackendConfig((prev) => ({
      ...prev,
      [key]: value || undefined, // Don't store empty strings
    }));
  };

  const generatePrompt = () => {
    const serviceNames = selectedServices
      .map((id) => serviceMap[id]?.name)
      .filter(Boolean);

    const enabledOptions = prodOptions
      .filter((opt) => productionOptions[opt.id])
      .map((opt) => opt.name.toLowerCase());

    let prompt = "";

    if (selectedPattern) {
      const pattern = patterns.find((p) => p.id === selectedPattern);
      if (pattern) {
        prompt = `${pattern.name} architecture`;
      }
    }

    if (serviceNames.length > 0) {
      prompt += prompt ? " with " : "";
      prompt += serviceNames.join(", ");
    }

    if (enabledOptions.length > 0) {
      prompt += ". Production-ready with " + enabledOptions.join(", ");
    }

    return prompt || "Describe your infrastructure...";
  };

  const handleGenerate = () => {
    const prompt = generatePrompt();
    if (selectedServices.length > 0) {
      onGenerate({
        prompt,
        provider,
        services: selectedServices,
        backend,
        backendConfig: backend !== "local" ? backendConfig : undefined,
        clarifications: {
          ...productionOptions,
          environment: productionOptions["high-availability"] ? "production" : "development",
        },
      });
    }
  };

  const providerNames: Record<Provider, string> = {
    aws: "AWS",
    gcp: "Google Cloud",
    azure: "Azure",
  };

  const handleImageGenerate = async (imageData: string, prompt: string) => {
    if (onGenerateFromImage) {
      await onGenerateFromImage({
        imageData,
        additionalContext: prompt,
        provider,
      });
    }
  };

  return (
    <div className="space-y-6">
      {/* Build Mode Toggle */}
      <div className="flex items-center justify-center gap-2 rounded-lg border border-border bg-muted/30 p-1">
        <button
          onClick={() => setBuildMode("services")}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
            buildMode === "services"
              ? "bg-background shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <Wand2 className="h-4 w-4" />
          Build from Services
        </button>
        <button
          onClick={() => setBuildMode("diagram")}
          className={`flex flex-1 items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-all ${
            buildMode === "diagram"
              ? "bg-background shadow-sm"
              : "text-muted-foreground hover:text-foreground"
          }`}
        >
          <ImageIcon className="h-4 w-4" />
          Upload Diagram
        </button>
      </div>

      {buildMode === "diagram" ? (
        <>
          {/* Provider Selection for Diagram */}
          <div>
            <h3 className="mb-3 text-sm font-medium text-muted-foreground">
              Target Cloud Provider
            </h3>
            <div className="flex gap-2">
              {(["aws", "gcp", "azure"] as Provider[]).map((p) => (
                <button
                  key={p}
                  onClick={() => setProvider(p)}
                  className={`flex-1 rounded-lg border-2 px-4 py-3 text-sm font-medium transition-all ${
                    provider === p
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  {providerNames[p]}
                </button>
              ))}
            </div>
          </div>

          {/* Image Upload Component */}
          <ImageUpload onGenerate={handleImageGenerate} isLoading={isLoading} />
        </>
      ) : (
        <>
          {/* Provider Selection */}
          <div>
            <h3 className="mb-3 text-sm font-medium text-muted-foreground">
              Cloud Provider
            </h3>
            <div className="flex gap-2">
              {(["aws", "gcp", "azure"] as Provider[]).map((p) => (
                <button
                  key={p}
                  onClick={() => handleProviderChange(p)}
                  className={`flex-1 rounded-lg border-2 px-4 py-3 text-sm font-medium transition-all ${
                    provider === p
                      ? "border-primary bg-primary/5 text-primary"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  {providerNames[p]}
                </button>
              ))}
            </div>
          </div>

      {/* Pattern Selection */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          Start with a Pattern (optional)
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
          {patterns.slice(0, 8).map((pattern) => (
            <button
              key={pattern.id}
              onClick={() => handlePatternSelect(pattern.id)}
              className={`flex flex-col items-center gap-2 rounded-lg border-2 p-3 text-center transition-all ${
                selectedPattern === pattern.id
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
            >
              <div
                className={`rounded-md p-2 ${
                  selectedPattern === pattern.id
                    ? "bg-primary text-primary-foreground"
                    : "bg-muted"
                }`}
              >
                {patternIcons[pattern.icon] || <Boxes className="h-5 w-5" />}
              </div>
              <span className="text-xs font-medium line-clamp-2">
                {pattern.name}
              </span>
            </button>
          ))}
        </div>
        {patterns.length > 8 && (
          <details className="mt-2">
            <summary className="cursor-pointer text-sm text-muted-foreground hover:text-foreground">
              Show {patterns.length - 8} more patterns...
            </summary>
            <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
              {patterns.slice(8).map((pattern) => (
                <button
                  key={pattern.id}
                  onClick={() => handlePatternSelect(pattern.id)}
                  className={`flex flex-col items-center gap-2 rounded-lg border-2 p-3 text-center transition-all ${
                    selectedPattern === pattern.id
                      ? "border-primary bg-primary/5"
                      : "border-border hover:border-primary/50"
                  }`}
                >
                  <div
                    className={`rounded-md p-2 ${
                      selectedPattern === pattern.id
                        ? "bg-primary text-primary-foreground"
                        : "bg-muted"
                    }`}
                  >
                    {patternIcons[pattern.icon] || <Boxes className="h-5 w-5" />}
                  </div>
                  <span className="text-xs font-medium line-clamp-2">
                    {pattern.name}
                  </span>
                </button>
              ))}
            </div>
          </details>
        )}
      </div>

      {/* Selected Services */}
      <div>
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-sm font-medium text-muted-foreground">
            Selected Services ({selectedServices.length})
          </h3>
          <Button
            variant="outline"
            size="sm"
            onClick={() => setShowServicePicker(!showServicePicker)}
          >
            <Plus className="mr-1 h-4 w-4" />
            Add Service
          </Button>
        </div>

        {/* Service Chips */}
        <div className="min-h-[60px] rounded-lg border border-dashed border-border bg-muted/30 p-3">
          {selectedServices.length === 0 ? (
            <p className="text-center text-sm text-muted-foreground">
              Select a pattern or add services manually
            </p>
          ) : (
            <div className="flex flex-wrap gap-2">
              {selectedServices.map((serviceId) => {
                const service = serviceMap[serviceId];
                if (!service) return null;
                return (
                  <div
                    key={serviceId}
                    className="flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1.5 text-sm"
                  >
                    {categoryIcons[service.category]}
                    <span>{service.name}</span>
                    <button
                      onClick={() => removeService(serviceId)}
                      className="ml-1 rounded-full p-0.5 hover:bg-primary/20"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Service Picker Dropdown */}
        {showServicePicker && (
          <div className="mt-2 rounded-lg border border-border bg-card p-3 shadow-lg">
            <div className="relative mb-3">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={serviceSearch}
                onChange={(e) => setServiceSearch(e.target.value)}
                placeholder="Search services..."
                className="pl-9"
                autoFocus
              />
            </div>
            <div className="max-h-[300px] overflow-y-auto">
              {categories.map((category) => {
                const categoryServices = groupedServices[category.id];
                if (!categoryServices || categoryServices.length === 0) return null;

                return (
                  <div key={category.id} className="mb-2">
                    <button
                      onClick={() =>
                        setExpandedCategory(
                          expandedCategory === category.id ? null : category.id
                        )
                      }
                      className="flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm font-medium hover:bg-muted"
                    >
                      <span className="flex items-center gap-2">
                        {categoryIcons[category.id]}
                        {category.name}
                        <span className="text-xs text-muted-foreground">
                          ({categoryServices.length})
                        </span>
                      </span>
                      <ChevronDown
                        className={`h-4 w-4 transition-transform ${
                          expandedCategory === category.id ? "rotate-180" : ""
                        }`}
                      />
                    </button>
                    {(expandedCategory === category.id || serviceSearch) && (
                      <div className="ml-6 mt-1 space-y-1">
                        {categoryServices.map((service) => {
                          const isSelected = selectedServices.includes(service.id);
                          return (
                            <button
                              key={service.id}
                              onClick={() => !isSelected && addService(service.id)}
                              disabled={isSelected}
                              className={`flex w-full items-center justify-between rounded-md px-2 py-1.5 text-sm ${
                                isSelected
                                  ? "bg-primary/10 text-muted-foreground"
                                  : "hover:bg-muted"
                              }`}
                            >
                              <span>
                                <span className="font-medium">{service.name}</span>
                                <span className="ml-2 text-xs text-muted-foreground">
                                  {service.description}
                                </span>
                              </span>
                              {isSelected && <Check className="h-4 w-4 text-primary" />}
                            </button>
                          );
                        })}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Production Options */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          Production Options
        </h3>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {prodOptions.map((option) => (
            <button
              key={option.id}
              onClick={() => toggleProductionOption(option.id)}
              className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition-all ${
                productionOptions[option.id]
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
            >
              <div
                className={`flex h-4 w-4 items-center justify-center rounded border ${
                  productionOptions[option.id]
                    ? "border-primary bg-primary text-primary-foreground"
                    : "border-muted-foreground"
                }`}
              >
                {productionOptions[option.id] && <Check className="h-3 w-3" />}
              </div>
              <span className="line-clamp-1">{option.name}</span>
            </button>
          ))}
        </div>
      </div>

      {/* State Backend */}
      <div>
        <h3 className="mb-3 text-sm font-medium text-muted-foreground">
          Terraform State Backend
        </h3>
        <div className="flex flex-wrap gap-2">
          {(
            [
              { id: "local", name: "Local", description: "Store state locally" },
              { id: "s3", name: "S3", description: "AWS S3 bucket" },
              { id: "gcs", name: "GCS", description: "Google Cloud Storage" },
              { id: "azurerm", name: "Azure Blob", description: "Azure Storage" },
              { id: "remote", name: "Terraform Cloud", description: "HCP Terraform" },
            ] as const
          ).map((opt) => (
            <button
              key={opt.id}
              onClick={() => handleBackendChange(opt.id)}
              className={`flex flex-col rounded-lg border-2 px-4 py-2 text-left transition-all ${
                backend === opt.id
                  ? "border-primary bg-primary/5"
                  : "border-border hover:border-primary/50"
              }`}
            >
              <span className="text-sm font-medium">{opt.name}</span>
              <span className="text-xs text-muted-foreground">{opt.description}</span>
            </button>
          ))}
        </div>

        {/* Backend Configuration Details */}
        {backend === "s3" && (
          <div className="mt-4 space-y-3 rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              Configure your S3 backend. Leave blank to generate commented placeholders.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium">Bucket Name</label>
                <Input
                  placeholder="my-terraform-state"
                  value={backendConfig.bucket || ""}
                  onChange={(e) => updateBackendConfig("bucket", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">State Key</label>
                <Input
                  placeholder="terraform.tfstate"
                  value={backendConfig.key || ""}
                  onChange={(e) => updateBackendConfig("key", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Region</label>
                <Input
                  placeholder="us-east-1"
                  value={backendConfig.region || ""}
                  onChange={(e) => updateBackendConfig("region", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">DynamoDB Table (optional)</label>
                <Input
                  placeholder="terraform-locks"
                  value={backendConfig.dynamodb_table || ""}
                  onChange={(e) => updateBackendConfig("dynamodb_table", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </div>
          </div>
        )}

        {backend === "gcs" && (
          <div className="mt-4 space-y-3 rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              Configure your GCS backend. Leave blank to generate commented placeholders.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium">Bucket Name</label>
                <Input
                  placeholder="my-terraform-state"
                  value={backendConfig.bucket || ""}
                  onChange={(e) => updateBackendConfig("bucket", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Prefix</label>
                <Input
                  placeholder="terraform/state"
                  value={backendConfig.prefix || ""}
                  onChange={(e) => updateBackendConfig("prefix", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </div>
          </div>
        )}

        {backend === "azurerm" && (
          <div className="mt-4 space-y-3 rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              Configure your Azure backend. Leave blank to generate commented placeholders.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium">Resource Group</label>
                <Input
                  placeholder="tfstate-rg"
                  value={backendConfig.resource_group_name || ""}
                  onChange={(e) => updateBackendConfig("resource_group_name", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Storage Account</label>
                <Input
                  placeholder="tfstatestorage"
                  value={backendConfig.storage_account_name || ""}
                  onChange={(e) => updateBackendConfig("storage_account_name", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Container Name</label>
                <Input
                  placeholder="tfstate"
                  value={backendConfig.container_name || ""}
                  onChange={(e) => updateBackendConfig("container_name", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">State Key</label>
                <Input
                  placeholder="terraform.tfstate"
                  value={backendConfig.key || ""}
                  onChange={(e) => updateBackendConfig("key", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </div>
          </div>
        )}

        {backend === "remote" && (
          <div className="mt-4 space-y-3 rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-xs text-muted-foreground">
              Configure your Terraform Cloud backend. Leave blank to generate commented placeholders.
            </p>
            <div className="grid gap-3 sm:grid-cols-2">
              <div>
                <label className="mb-1 block text-xs font-medium">Organization</label>
                <Input
                  placeholder="my-org"
                  value={backendConfig.organization || ""}
                  onChange={(e) => updateBackendConfig("organization", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
              <div>
                <label className="mb-1 block text-xs font-medium">Workspace</label>
                <Input
                  placeholder="my-workspace"
                  value={backendConfig.workspace || ""}
                  onChange={(e) => updateBackendConfig("workspace", e.target.value)}
                  className="h-9 text-sm"
                />
              </div>
            </div>
          </div>
        )}
      </div>

          {/* Preview & Generate */}
          <div className="rounded-lg border border-border bg-muted/30 p-4">
            <h3 className="mb-2 text-sm font-medium text-muted-foreground">
              Preview
            </h3>
            <p className="mb-4 text-sm italic">&quot;{generatePrompt()}&quot;</p>
            <Button
              onClick={handleGenerate}
              disabled={selectedServices.length === 0}
              className="w-full"
              size="lg"
            >
              Generate Terraform
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
