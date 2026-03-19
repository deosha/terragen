"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import {
  GitBranch,
  Loader2,
  Send,
  ExternalLink,
  CheckCircle2,
} from "lucide-react";
import { Header } from "@/components/Header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { CodePreview } from "@/components/CodePreview";
import { useAuth } from "@/hooks/useAuth";
import { api, Repository, ModifyResponse } from "@/lib/api";

export default function ModifyPage() {
  const router = useRouter();
  const { user, loading, login, logout, isAuthenticated, providers, providersLoading } = useAuth();

  const [repos, setRepos] = useState<Repository[]>([]);
  const [selectedRepo, setSelectedRepo] = useState<string>("");
  const [prompt, setPrompt] = useState("");
  const [modifying, setModifying] = useState(false);
  const [result, setResult] = useState<ModifyResponse | null>(null);
  const [loadingRepos, setLoadingRepos] = useState(true);

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push("/");
    }
  }, [loading, isAuthenticated, router]);

  useEffect(() => {
    if (isAuthenticated) {
      loadRepos();
    }
  }, [isAuthenticated]);

  const loadRepos = async () => {
    try {
      const repos = await api.listRepos();
      setRepos(repos);
    } catch (error) {
      console.error("Failed to load repos:", error);
    } finally {
      setLoadingRepos(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedRepo || !prompt.trim() || modifying) return;

    const repo = repos.find((r) => r.full_name === selectedRepo);
    if (!repo) return;

    setModifying(true);
    setResult(null);

    try {
      const response = await api.modify({
        prompt,
        repo: {
          owner: repo.owner,
          repo: repo.name,
          branch: repo.default_branch,
          path: ".",
        },
        create_pr: true,
      });

      // Poll for completion
      let status: ModifyResponse;
      do {
        await new Promise((resolve) => setTimeout(resolve, 2000));
        status = await api.getModifyStatus(response.session_id);
        setResult(status);
      } while (
        status.status === "pending" ||
        status.status === "cloning" ||
        status.status === "modifying" ||
        status.status === "creating_pr"
      );
    } catch (error) {
      console.error("Modify error:", error);
    } finally {
      setModifying(false);
    }
  };

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return null;
  }

  return (
    <div className="flex h-screen flex-col">
      <Header user={user} onLogin={login} onLogout={logout} providers={providers} providersLoading={providersLoading} />

      <main className="flex-1 overflow-y-auto p-4">
        <div className="mx-auto max-w-3xl">
          <div className="mb-6">
            <h1 className="text-2xl font-bold">Modify Existing Infrastructure</h1>
            <p className="mt-1 text-muted-foreground">
              Select a repository and describe the changes you want to make
            </p>
          </div>

          <Card className="mb-6">
            <CardHeader>
              <CardTitle className="text-lg">Repository</CardTitle>
            </CardHeader>
            <CardContent>
              {loadingRepos ? (
                <div className="flex items-center gap-2 text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  Loading repositories...
                </div>
              ) : (
                <Select value={selectedRepo} onValueChange={setSelectedRepo}>
                  <SelectTrigger>
                    <SelectValue placeholder="Select a repository" />
                  </SelectTrigger>
                  <SelectContent>
                    {repos.map((repo) => (
                      <SelectItem key={repo.full_name} value={repo.full_name}>
                        <div className="flex items-center gap-2">
                          <GitBranch className="h-4 w-4" />
                          {repo.full_name}
                          {repo.private && (
                            <span className="text-xs text-muted-foreground">
                              (private)
                            </span>
                          )}
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </CardContent>
          </Card>

          <form onSubmit={handleSubmit} className="mb-6">
            <div className="flex gap-2">
              <Input
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                placeholder="Describe the changes you want to make..."
                className="flex-1"
                disabled={modifying || !selectedRepo}
              />
              <Button
                type="submit"
                disabled={modifying || !selectedRepo || !prompt.trim()}
              >
                {modifying ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
              </Button>
            </div>
          </form>

          {result && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2 text-lg">
                  {result.status === "completed" ? (
                    <>
                      <CheckCircle2 className="h-5 w-5 text-green-500" />
                      Changes Applied
                    </>
                  ) : result.status === "error" ? (
                    "Error"
                  ) : (
                    <>
                      <Loader2 className="h-5 w-5 animate-spin" />
                      {result.status === "cloning"
                        ? "Cloning repository..."
                        : result.status === "modifying"
                        ? "Applying changes..."
                        : result.status === "creating_pr"
                        ? "Creating pull request..."
                        : "Processing..."}
                    </>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent>
                {result.pr_url && (
                  <div className="mb-4">
                    <a
                      href={result.pr_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-2 text-primary hover:underline"
                    >
                      View Pull Request
                      <ExternalLink className="h-4 w-4" />
                    </a>
                  </div>
                )}

                {result.changes && Object.keys(result.changes).length > 0 && (
                  <div>
                    <h4 className="mb-2 font-medium">Changed Files</h4>
                    <CodePreview
                      files={Object.fromEntries(
                        Object.entries(result.changes).map(([name, change]) => [
                          name,
                          change.new,
                        ])
                      )}
                      changes={result.changes}
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </div>
      </main>
    </div>
  );
}
