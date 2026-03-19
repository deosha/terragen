"use client";

import Image from "next/image";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { LogOut, Github, Terminal, Sparkles, GitBranch, BookOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import { User, GitProvider, ProviderInfo } from "@/lib/api";

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

interface HeaderProps {
  user: User | null;
  onLogin: (provider: GitProvider) => void;
  onLogout: () => void;
  providers?: ProviderInfo[];
  providersLoading?: boolean;
}

export function Header({ user, onLogin, onLogout, providers = [], providersLoading = false }: HeaderProps) {
  const pathname = usePathname();

  return (
    <header className="border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="container flex h-14 max-w-screen-2xl items-center">
        <Link href="/" className="flex items-center gap-2 font-semibold">
          <Terminal className="h-5 w-5 text-primary" />
          <span>TerraGen</span>
        </Link>

        {/* Navigation */}
        {user && (
          <nav className="ml-8 flex items-center gap-1">
            <Link
              href="/"
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                pathname === "/"
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <Sparkles className="h-4 w-4" />
              Generate
            </Link>
            <Link
              href="/modify"
              className={`flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                pathname === "/modify"
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
            >
              <GitBranch className="h-4 w-4" />
              Modify
            </Link>
            <a
              href={`${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/docs`}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <BookOpen className="h-4 w-4" />
              API Docs
            </a>
          </nav>
        )}

        <div className="flex flex-1 items-center justify-end space-x-4">
          {user ? (
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-2">
                {user.avatar_url && (
                  <Image
                    src={user.avatar_url}
                    alt={user.username}
                    width={32}
                    height={32}
                    className="rounded-full"
                  />
                )}
                <div className="flex flex-col">
                  <span className="text-sm text-muted-foreground">
                    {user.name || user.username}
                  </span>
                  {user.provider && (
                    <span className="flex items-center gap-1 text-xs text-muted-foreground/70">
                      <ProviderIcon provider={user.provider} className="h-3 w-3" />
                      {user.provider.charAt(0).toUpperCase() + user.provider.slice(1)}
                    </span>
                  )}
                </div>
              </div>
              <Button variant="ghost" size="icon" onClick={onLogout}>
                <LogOut className="h-4 w-4" />
              </Button>
            </div>
          ) : providersLoading ? (
            <div className="h-9 w-32 animate-pulse rounded-md bg-muted" />
          ) : providers.length === 1 ? (
            <Button onClick={() => onLogin(providers[0].id)}>
              <ProviderIcon provider={providers[0].icon} className="mr-2 h-4 w-4" />
              Sign in with {providers[0].name}
            </Button>
          ) : (
            <div className="flex gap-2">
              {providers.map((provider) => (
                <Button
                  key={provider.id}
                  variant="outline"
                  size="sm"
                  onClick={() => onLogin(provider.id)}
                >
                  <ProviderIcon provider={provider.icon} className="mr-2 h-4 w-4" />
                  {provider.name}
                </Button>
              ))}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
