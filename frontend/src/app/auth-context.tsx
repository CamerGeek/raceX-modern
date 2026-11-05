"use client";

import { createClient, type Session, type SupabaseClient } from "@supabase/supabase-js";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { useMessages } from "../i18n/provider";
import { offlineKeys, readOffline, removeOfflineKeys, saveOffline } from "./offline-data";

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
  offlineAccess: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  signUp: (email: string, password: string, phone: string) => Promise<SignUpResult>;
  signOut: () => Promise<void>;
  apiFetch: (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;
  refreshProfile: () => Promise<void>;
};

export type SignUpResult = {
  hasSession: boolean;
  identityCreated: boolean;
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
  const t = useMessages().auth;
  const client = getSupabaseClient();
  const [session, setSession] = useState<Session | null>(null);
  const [profile, setProfile] = useState<AccountProfile | null>(null);
  const [profileError, setProfileError] = useState("");
  const [offlineAccess, setOfflineAccess] = useState(false);
  const [loading, setLoading] = useState(true);

  const loadProfile = useCallback(async (accessToken: string | null, userId: string | null) => {
    if (!accessToken || !userId) {
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        const cached = await readOffline<AccountProfile>(offlineKeys.lastProfile);
        if (cached) {
          setProfile(cached.payload);
          setProfileError("");
          setOfflineAccess(true);
          setLoading(false);
          return;
        }
      }
      setProfile(null);
      setProfileError("");
      setOfflineAccess(false);
      setLoading(false);
      return;
    }
    try {
      const response = await fetch(`${apiUrl}/api/v1/auth/profile`, {
        headers: { Authorization: `Bearer ${accessToken}` },
        cache: "no-store",
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? t.profileError);
      const nextProfile = payload as AccountProfile;
      setProfile(nextProfile);
      setProfileError("");
      setOfflineAccess(false);
      void saveOffline(offlineKeys.profile(nextProfile.id), nextProfile);
      void saveOffline(offlineKeys.lastProfile, nextProfile);
    } catch (error) {
      const cached = await readOffline<AccountProfile>(offlineKeys.profile(userId))
        ?? await readOffline<AccountProfile>(offlineKeys.lastProfile);
      if (cached) {
        setProfile(cached.payload);
        setProfileError("");
        setOfflineAccess(true);
      } else {
        setProfile(null);
        setOfflineAccess(false);
        setProfileError(error instanceof Error ? error.message : t.profileError);
      }
    } finally {
      setLoading(false);
    }
  }, [t.profileError]);

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
        if (active) {
          void loadProfile(nextSession?.access_token ?? null, nextSession?.user.id ?? null);
        }
      }, 0);
    });
    void client.auth.getSession().then(({ data, error }) => {
      if (!active) return;
      if (error) setProfileError(error.message);
      setSession(data.session);
      void loadProfile(data.session?.access_token ?? null, data.session?.user.id ?? null);
    });
    return () => {
      active = false;
      subscription.unsubscribe();
    };
  }, [client, loadProfile]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (!client) throw new Error(t.notConfigured);
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, [client, t.notConfigured]);

  const signUp = useCallback(async (email: string, password: string, phone: string) => {
    if (!client) throw new Error(t.notConfigured);
    const { data, error } = await client.auth.signUp({
      email,
      password,
      options: {
        data: { phone: phone.trim() },
        emailRedirectTo: `${window.location.origin}/account`,
      },
    });
    if (error) throw error;
    return {
      hasSession: Boolean(data.session),
      identityCreated: Boolean(data.user?.identities?.length),
    };
  }, [client, t.notConfigured]);

  const signOut = useCallback(async () => {
    if (!client) return;
    const previousUserId = session?.user.id ?? profile?.id;
    setProfile(null);
    setOfflineAccess(false);
    setProfileError("");
    if (previousUserId) {
      void removeOfflineKeys([offlineKeys.analysisPrefix(previousUserId), offlineKeys.profile(previousUserId)]);
    }
    void removeOfflineKeys([offlineKeys.lastProfile]);
    const { error } = await client.auth.signOut();
    if (error) throw error;
  }, [client, profile?.id, session?.user.id]);

  const apiFetch = useCallback(async (input: RequestInfo | URL, init?: RequestInit) => {
    if (!session?.access_token) throw new Error(t.signInRequired);
    const headers = new Headers(init?.headers);
    headers.set("Authorization", `Bearer ${session.access_token}`);
    return fetch(input, { ...init, headers });
  }, [session, t.signInRequired]);

  const refreshProfile = useCallback(async () => {
    await loadProfile(session?.access_token ?? null, session?.user.id ?? null);
  }, [loadProfile, session]);

  const value = useMemo<AuthContextValue>(() => ({
    configured: Boolean(client),
    loading,
    session,
    profile,
    profileError,
    offlineAccess,
    signIn,
    signUp,
    signOut,
    apiFetch,
    refreshProfile,
  }), [apiFetch, client, loading, offlineAccess, profile, profileError, refreshProfile, session, signIn, signOut, signUp]);

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth must be used within AuthProvider");
  return context;
}
