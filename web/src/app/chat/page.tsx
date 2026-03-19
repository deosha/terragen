"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { Header } from "@/components/Header";
import { ChatInterface } from "@/components/ChatInterface";
import { useAuth } from "@/hooks/useAuth";

export default function ChatPage() {
  const router = useRouter();
  const { user, loading, login, logout, isAuthenticated, providers, providersLoading } = useAuth();

  useEffect(() => {
    if (!loading && !isAuthenticated) {
      router.push("/");
    }
  }, [loading, isAuthenticated, router]);

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
      <ChatInterface />
    </div>
  );
}
