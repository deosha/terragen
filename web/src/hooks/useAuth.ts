"use client";

import { useState, useEffect, useCallback } from "react";
import { api, User, GitProvider, ProviderInfo } from "@/lib/api";

export function useAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [providers, setProviders] = useState<ProviderInfo[]>([]);
  const [providersLoading, setProvidersLoading] = useState(true);

  const checkAuth = useCallback(async () => {
    const token = api.getToken();
    if (!token) {
      setLoading(false);
      return;
    }

    try {
      const user = await api.getMe();
      setUser(user);
    } catch {
      api.setToken(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchProviders = useCallback(async () => {
    try {
      const { providers } = await api.getProviders();
      setProviders(providers);
    } catch {
      // Default to GitHub if providers endpoint fails
      setProviders([{ id: "github", name: "GitHub", icon: "github" }]);
    } finally {
      setProvidersLoading(false);
    }
  }, []);

  useEffect(() => {
    checkAuth();
    fetchProviders();
  }, [checkAuth, fetchProviders]);

  const login = useCallback(async (provider: GitProvider = "github") => {
    // Store provider in sessionStorage for callback
    sessionStorage.setItem("auth_provider", provider);
    const { url } = await api.getLoginUrl(provider);
    window.location.href = url;
  }, []);

  const logout = useCallback(() => {
    api.setToken(null);
    setUser(null);
    sessionStorage.removeItem("auth_provider");
    window.location.href = "/";
  }, []);

  const handleCallback = useCallback(async (code: string, provider?: GitProvider) => {
    // Get provider from parameter or sessionStorage
    const authProvider = provider || (sessionStorage.getItem("auth_provider") as GitProvider) || "github";
    const { access_token, user } = await api.exchangeCode(code, authProvider);
    api.setToken(access_token);
    setUser(user);
    sessionStorage.removeItem("auth_provider");
  }, []);

  return {
    user,
    loading,
    login,
    logout,
    handleCallback,
    isAuthenticated: !!user,
    providers,
    providersLoading,
  };
}
