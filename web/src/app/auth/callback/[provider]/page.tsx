"use client";

import { Suspense, useEffect, useState, useRef } from "react";
import { useRouter, useSearchParams, useParams } from "next/navigation";
import { useAuth } from "@/hooks/useAuth";
import { GitProvider } from "@/lib/api";

function AuthCallbackContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams();
  const { handleCallback } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [processing, setProcessing] = useState(true);
  const calledRef = useRef(false);

  const provider = params.provider as GitProvider;

  useEffect(() => {
    if (calledRef.current) return;

    const code = searchParams.get("code");
    const errorParam = searchParams.get("error");

    if (errorParam) {
      setError(searchParams.get("error_description") || "Authentication failed");
      setProcessing(false);
      return;
    }

    if (!code) {
      // Wait a moment - searchParams might not be ready yet
      const timeout = setTimeout(() => {
        if (!searchParams.get("code")) {
          setError("No authorization code received");
          setProcessing(false);
        }
      }, 2000);
      return () => clearTimeout(timeout);
    }

    calledRef.current = true;
    setProcessing(true);
    handleCallback(code, provider)
      .then(() => {
        router.push("/chat");
      })
      .catch((err) => {
        setError(err.message || "Authentication failed");
        setProcessing(false);
      });
  }, [searchParams, handleCallback, router, provider]);

  if (processing && !error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
        <p className="text-muted-foreground">Completing sign in...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-4">
        <h1 className="text-xl font-semibold text-red-500">
          Authentication Error
        </h1>
        <p className="text-muted-foreground">{error}</p>
        <a href="/" className="text-primary underline">
          Go back to home
        </a>
      </div>
    );
  }

  return (
    <div className="flex h-screen flex-col items-center justify-center gap-4">
      <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
      <p className="text-muted-foreground">Redirecting...</p>
    </div>
  );
}

export default function AuthCallback() {
  return (
    <Suspense
      fallback={
        <div className="flex h-screen flex-col items-center justify-center gap-4">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-primary border-t-transparent" />
          <p className="text-muted-foreground">Loading...</p>
        </div>
      }
    >
      <AuthCallbackContent />
    </Suspense>
  );
}
