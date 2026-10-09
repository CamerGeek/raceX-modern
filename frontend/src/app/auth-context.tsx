"use client";

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

export type AccessRole = "simple" | "demo" | "subscriber" | "admin";
export type AccountProfile = {
  id: string;
  email: string;
  phone: string | null;
  role: AccessRole;
  stored_role: AccessRole;
  demo_expires_at: string | null;
  subscriber_expires_at: string | null;
};

type AuthContextValue = {
  configured: boolean;
  loading: boolean;
  session: Session | null;
  profile: AccountProfile | null;
  profileError: string;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, phone: string) => Promise<boolean>;
  signOut: () => Promise<void>;
  apiFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  refreshProfile: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);
let supabaseClient: SupabaseClient | null = null;

function getSupabaseClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  if (!url || !key) return null;
  if (!supabaseClient) supabaseClient = createClient(url, key);
  return supabaseClient;
}

const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function AuthProvider({ children }: Readonly<{ children: React.ReactNode }>) {
  const client = getSupabaseClient();
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [profileError, setProfileError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (accessToken: string | null) => {
    if (!accessToken) {
      setProfile(null);
      setProfileError("");
      setLoading(false);
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/profile`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? "Impossible de charger votre compte.");
      setProfile(payload as AccountProfile);
      setProfileError("");
    } catch (error) {
      setProfile(null);
      setProfileError(error instanceof Error ? error.message : "Impossible de charger votre compte.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (!client) {
      const timer = window.setTimeout(() => setLoading(false), 0);
      return () => window.clearTimeout(timer);
    }
    let active = true;
    const { data: { subscription } } = client.auth.onAuthStateChange((_event, nextSession) => {
      if (!active) return;
      setSession(nextSession);
      window.setTimeout(() => {
        if (active) void loadProfile(nextSession?.access_token ?? null);
      }, 0);
    });
    void client.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) setProfileError(error.message);
      setSession(data.session);
      void loadProfile(data.session?.access_token ?? null);
    });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [client, loadProfile]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!client) throw new Error("L’authentification Supabase n’est pas configurée.");
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, [client]);

  const signUp = useCallback(async (email: string, password: string, phone: string) => {
    if (!client) throw new Error("L’authentification Supabase n’est pas configurée.");
    const { data, error } = await client.auth.signUp({
      email,
      password,
      options: { data: { phone: phone.trim() } },
    });
    if (error) throw error;
    return Boolean(data.session);
  }, [client]);

  const signOut = useCallback(async () => {
    if (!client) return;
    const { error } = await client.auth.signOut();
    if (error) throw error;
  }, [client]);

  const apiFetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!session?.access_token) throw new Error("Connectez-vous pour continuer.");
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${session.access_token}`);
    return fetch(input, { ...init, headers });
  }, [session]);

  const refreshProfile = useCallback(async () => {
    await loadProfile(session?.access_token ?? null);
  }, [loadProfile, session]);

  const value = useMemo<AuthContextValue>(() => ({
    configured: Boolean(client),
    loading,
    session,
    profile,
    profileError,
    signIn,
    signUp,
    signOut,
    apiFetch,
    refreshProfile,
  }), [apiFetch, client, loading, profile, profileError, refreshProfile, session, signIn, signOut, signUp]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
