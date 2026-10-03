"use client";

import { createClient, type SupabaseClient } from "@supabase/supabase-js";

declare global {
  interface Window {
    __ORIGINSYNC_CONFIG__?: {
      supabaseUrl: string | null;
      supabaseAnonKey: string | null;
    };
  }
}

let client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient | null {
  const runtimeConfig =
    typeof window === "undefined" ? undefined : window.__ORIGINSYNC_CONFIG__;
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL || runtimeConfig?.supabaseUrl;
  const anonKey =
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || runtimeConfig?.supabaseAnonKey;
  if (!url || !anonKey) return null;
  client ??= createClient(url, anonKey, {
    auth: {
      autoRefreshToken: true,
      persistSession: true,
      detectSessionInUrl: true,
    },
  });
  return client;
}

export function subscribeToSupabaseConfig(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener("originsync-config-ready", onChange);
  return () => window.removeEventListener("originsync-config-ready", onChange);
}
