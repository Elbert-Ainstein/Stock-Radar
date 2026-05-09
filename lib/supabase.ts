import { createClient, SupabaseClient } from "@supabase/supabase-js";

const supabaseUrl = process.env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseKey = process.env.SUPABASE_ANON_KEY || process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

// Lazy-init: only create the client when actually called (server-side).
// This prevents the module from crashing at import time on the client,
// where env vars are unavailable.
let _client: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient {
  if (_client) return _client;
  if (!supabaseUrl || !supabaseKey) {
    throw new Error(
      "[supabase] SUPABASE_URL or SUPABASE_ANON_KEY not set — cannot create client"
    );
  }
  _client = createClient(supabaseUrl, supabaseKey);
  return _client;
}

// Keep the named export for backward compat — but as a getter proxy
// so it only calls createClient when a property is accessed, not at import time.
export const supabase = new Proxy({} as SupabaseClient, {
  get(_target, prop, receiver) {
    return Reflect.get(getSupabase(), prop, receiver);
  },
});
