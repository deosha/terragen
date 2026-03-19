const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export type GitProvider = 'github' | 'gitlab' | 'bitbucket';

export interface User {
  username: string;
  email: string | null;
  name: string | null;
  avatar_url: string | null;
  provider?: GitProvider;
}

export interface ProviderInfo {
  id: GitProvider;
  name: string;
  icon: string;
}

export interface BackendConfig {
  type: string;
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

export interface GenerateRequest {
  prompt: string;
  provider: string;
  region?: string;
  backend?: string;
  backendConfig?: BackendConfig;
  options?: Record<string, unknown>;
  clarifications?: Record<string, unknown>;
}

export interface AnalyzeImageRequest {
  image_data: string;
  additional_context?: string;
}

export interface AnalyzeImageResponse {
  analysis: string;
  cloud_provider?: string;
  components: Array<{ name: string; description: string }>;
  networking?: string;
  data_flow?: string;
  additional_requirements?: string;
}

export interface GenerateFromImageRequest {
  image_data: string;  // Base64 encoded image (with or without data URI prefix)
  additional_context?: string;
  provider?: string;
  region?: string;
  backend?: string;
  backendConfig?: BackendConfig;
  skip_cost?: boolean;
  max_security_fixes?: number;
  confirmed_analysis?: string;  // Pre-confirmed analysis to skip re-analyzing
}

export interface LogEntry {
  timestamp: string;
  level: 'info' | 'success' | 'warning' | 'error';
  agent?: string;
  message: string;
  details?: string;
}

export interface GenerateResponse {
  session_id: string;
  status: string;
  files?: Record<string, string>;
  cost_estimate?: {
    monthly_cost: string;
    breakdown: Array<{ name: string; monthly_cost: string }>;
  };
  security_issues?: Array<{
    severity: string;
    rule_id: string;
    description: string;
    location: string;
    file_path?: string;
    line_number?: number;
  }>;
  validation_errors?: Array<{
    type: string;
    message: string;
    file_path?: string;
    line_number?: number;
  }>;
  plan?: string;
  current_agent?: string;
  fix_attempt?: number;
  max_fix_attempts?: number;
  logs?: LogEntry[];
  pipeline_summary?: Record<string, unknown>;
  error?: string;
}

export interface ModifyRequest {
  prompt: string;
  repo: {
    owner: string;
    repo: string;
    branch: string;
    path: string;
  };
  create_pr: boolean;
}

export interface ModifyResponse {
  session_id: string;
  status: string;
  branch?: string;
  pr_url?: string;
  changes?: Record<string, { old: string; new: string }>;
  plan?: string;
}

export interface ValidateResponse {
  valid: boolean;
  format_ok: boolean;
  errors: string[];
  warnings: string[];
}

export interface CostResponse {
  monthly_cost?: string;
  breakdown?: Array<{ name: string; monthly_cost: string }>;
  error?: string;
}

export interface SecurityResponse {
  issues: Array<{
    severity: string;
    rule_id: string;
    description: string;
    location: string;
    line: number;
  }>;
  passed: number;
  failed: number;
}

export interface PlanResponse {
  success: boolean;
  plan_output?: string;
  resource_changes?: Array<{
    address: string;
    type: string;
    name: string;
    actions: string[];
  }>;
  error?: string;
}

export interface Repository {
  owner: string;
  name: string;
  full_name: string;
  default_branch: string;
  private: boolean;
}

class ApiClient {
  private token: string | null = null;

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
    } else {
      localStorage.removeItem('token');
    }
  }

  getToken(): string | null {
    if (!this.token && typeof window !== 'undefined') {
      this.token = localStorage.getItem('token');
    }
    return this.token;
  }

  private async fetch<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const token = this.getToken();

    const response = await fetch(`${API_URL}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...options.headers,
      },
    });

    if (!response.ok) {
      if (response.status === 401) {
        this.setToken(null);
        window.location.href = '/';
      }
      const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
      throw new Error(error.detail || 'Request failed');
    }

    return response.json();
  }

  // Auth
  async getProviders(): Promise<{ providers: ProviderInfo[] }> {
    return this.fetch('/auth/providers');
  }

  async getLoginUrl(provider: GitProvider): Promise<{ url: string; provider: string }> {
    return this.fetch(`/auth/login/${provider}`);
  }

  async exchangeCode(code: string, provider: GitProvider): Promise<{ access_token: string; user: User }> {
    return this.fetch('/auth/callback', {
      method: 'POST',
      body: JSON.stringify({ code, provider }),
    });
  }

  async getMe(): Promise<User> {
    return this.fetch('/me');
  }

  // Generate
  async getClarifyingQuestions(
    prompt: string,
    provider: string
  ): Promise<{ questions: Array<{ id: string; question: string; options: string[]; default?: string }> }> {
    return this.fetch('/generate/clarify', {
      method: 'POST',
      body: JSON.stringify({ prompt, provider }),
    });
  }

  async generate(request: GenerateRequest): Promise<GenerateResponse> {
    return this.fetch('/generate/', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async analyzeImage(request: AnalyzeImageRequest): Promise<AnalyzeImageResponse> {
    return this.fetch('/generate/analyze-image', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async generateFromImage(request: GenerateFromImageRequest): Promise<GenerateResponse> {
    return this.fetch('/generate/from-image', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getGenerateStatus(sessionId: string): Promise<GenerateResponse> {
    return this.fetch(`/generate/${sessionId}`);
  }

  streamGenerate(sessionId: string): EventSource {
    const token = this.getToken();
    return new EventSource(
      `${API_URL}/generate/${sessionId}/stream?token=${token}`
    );
  }

  // Modify
  async listRepos(): Promise<Repository[]> {
    return this.fetch('/modify/repos');
  }

  async modify(request: ModifyRequest): Promise<ModifyResponse> {
    return this.fetch('/modify/', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  async getModifyStatus(sessionId: string): Promise<ModifyResponse> {
    return this.fetch(`/modify/${sessionId}`);
  }

  // Validate
  async validate(files: Record<string, string>): Promise<ValidateResponse> {
    return this.fetch('/validate/', {
      method: 'POST',
      body: JSON.stringify({ files }),
    });
  }

  async estimateCost(files: Record<string, string>): Promise<CostResponse> {
    return this.fetch('/validate/cost', {
      method: 'POST',
      body: JSON.stringify({ files }),
    });
  }

  async securityScan(files: Record<string, string>): Promise<SecurityResponse> {
    return this.fetch('/validate/security', {
      method: 'POST',
      body: JSON.stringify({ files }),
    });
  }

  async plan(files: Record<string, string>): Promise<PlanResponse> {
    return this.fetch('/validate/plan', {
      method: 'POST',
      body: JSON.stringify({ files }),
    });
  }

  async updateSessionFiles(
    sessionId: string,
    files: Record<string, string>
  ): Promise<{ status: string; message: string }> {
    return this.fetch(`/generate/${sessionId}/files`, {
      method: 'PUT',
      body: JSON.stringify({ files }),
    });
  }
}

export const api = new ApiClient();
