"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Terminal, Github, ArrowRight, Zap, Shield, DollarSign, Image, ClipboardList, FileCode } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { useAuth } from "@/hooks/useAuth";
import { GitProvider } from "@/lib/api";

// Provider icons (inline SVGs for GitLab and Bitbucket)
function GitLabIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M22.65 14.39L12 22.13 1.35 14.39a.84.84 0 01-.3-.94l1.22-3.78 2.44-7.51A.42.42 0 014.82 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.49h8.1l2.44-7.51A.42.42 0 0118.6 2a.43.43 0 01.58 0 .42.42 0 01.11.18l2.44 7.51L23 13.45a.84.84 0 01-.35.94z"/>
    </svg>
  );
}

function BitbucketIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="currentColor">
      <path d="M.778 1.211c-.424-.006-.772.334-.778.758 0 .063.006.126.019.189l3.25 19.68c.087.477.503.826.988.838h15.75c.363.007.678-.258.738-.619l3.253-19.903a.771.771 0 00-.618-.912.776.776 0 00-.147-.019zM14.52 15.53H9.522L8.17 8.469h7.561z"/>
    </svg>
  );
}

function ProviderIcon({ provider, className }: { provider: string; className?: string }) {
  switch (provider) {
    case "github":
      return <Github className={className} />;
    case "gitlab":
      return <GitLabIcon className={className} />;
    case "bitbucket":
      return <BitbucketIcon className={className} />;
    default:
      return <Github className={className} />;
  }
}

export default function Home() {
  const router = useRouter();
  const { user, loading, login, isAuthenticated, providers, providersLoading } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      router.push("/chat");
    }
  }, [isAuthenticated, router]);

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  const handleLogin = (provider: GitProvider) => {
    login(provider);
  };

  return (
    <div className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="border-b">
        <div className="container flex h-14 items-center">
          <div className="flex items-center gap-2 font-semibold">
            <Terminal className="h-5 w-5 text-primary" />
            <span>TerraGen</span>
          </div>
          <div className="ml-auto flex gap-2">
            {providersLoading ? (
              <div className="h-9 w-32 animate-pulse rounded-md bg-muted" />
            ) : providers.length === 1 ? (
              <Button onClick={() => handleLogin(providers[0].id)}>
                <ProviderIcon provider={providers[0].icon} className="mr-2 h-4 w-4" />
                Sign in with {providers[0].name}
              </Button>
            ) : (
              providers.map((provider) => (
                <Button
                  key={provider.id}
                  variant="outline"
                  onClick={() => handleLogin(provider.id)}
                >
                  <ProviderIcon provider={provider.icon} className="mr-2 h-4 w-4" />
                  {provider.name}
                </Button>
              ))
            )}
          </div>
        </div>
      </header>

      {/* Hero */}
      <main className="flex-1">
        <section className="container flex flex-col items-center justify-center gap-6 py-20 text-center">
          <h1 className="text-4xl font-bold tracking-tight sm:text-5xl md:text-6xl">
            Generate Terraform with{" "}
            <span className="text-primary">Natural Language</span>
          </h1>
          <p className="max-w-2xl text-lg text-muted-foreground">
            Describe your infrastructure in plain English or upload architecture diagrams.
            TerraGen uses AI to generate production-ready Terraform code with validation,
            security scanning, and cost estimation built-in.
          </p>
          <div className="flex gap-4">
            {providers.length > 0 && (
              <Button size="lg" onClick={() => handleLogin(providers[0].id)}>
                Get Started
                <ArrowRight className="ml-2 h-4 w-4" />
              </Button>
            )}
            <Button size="lg" variant="outline">
              View Examples
            </Button>
          </div>
        </section>

        {/* Features */}
        <section className="container py-20">
          <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <Zap className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Instant Generation</h3>
                <p className="text-sm text-muted-foreground">
                  Generate complete Terraform configurations in seconds. Just
                  describe what you need.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <Image className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Diagram to Code</h3>
                <p className="text-sm text-muted-foreground">
                  Upload AWS/GCP/Azure architecture diagrams and get Terraform code
                  automatically.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <Shield className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Security Scanning</h3>
                <p className="text-sm text-muted-foreground">
                  Scan with tfsec, Checkov, and OPA policies. Fix vulnerabilities
                  before deployment.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <ClipboardList className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Terraform Plan</h3>
                <p className="text-sm text-muted-foreground">
                  Preview resource changes before applying. See what will be
                  created, modified, or deleted.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <DollarSign className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Cost Estimation</h3>
                <p className="text-sm text-muted-foreground">
                  Know your costs before you deploy. Integrated cost estimation
                  with Infracost.
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardContent className="flex flex-col items-center gap-4 p-6 text-center">
                <div className="rounded-full bg-primary/10 p-3">
                  <FileCode className="h-6 w-6 text-primary" />
                </div>
                <h3 className="text-lg font-semibold">Inline Editor</h3>
                <p className="text-sm text-muted-foreground">
                  Edit generated code directly in the browser with syntax
                  highlighting and validation.
                </p>
              </CardContent>
            </Card>
          </div>
        </section>

        {/* CTA */}
        <section className="border-t bg-muted/50">
          <div className="container flex flex-col items-center gap-6 py-20 text-center">
            <h2 className="text-3xl font-bold">Ready to get started?</h2>
            <p className="text-muted-foreground">
              Sign in with your preferred Git provider to start generating infrastructure.
            </p>
            <div className="flex flex-wrap justify-center gap-3">
              {providersLoading ? (
                <div className="h-10 w-48 animate-pulse rounded-md bg-muted" />
              ) : (
                providers.map((provider) => (
                  <Button
                    key={provider.id}
                    size="lg"
                    variant={providers.length === 1 ? "default" : "outline"}
                    onClick={() => handleLogin(provider.id)}
                  >
                    <ProviderIcon provider={provider.icon} className="mr-2 h-4 w-4" />
                    Continue with {provider.name}
                  </Button>
                ))
              )}
            </div>
          </div>
        </section>
      </main>

      {/* Footer */}
      <footer className="border-t py-6">
        <div className="container flex items-center justify-between text-sm text-muted-foreground">
          <p>TerraGen - AI-powered Terraform generator</p>
          <p>Built with Claude</p>
        </div>
      </footer>
    </div>
  );
}
