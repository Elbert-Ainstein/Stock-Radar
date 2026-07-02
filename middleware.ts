// Minimal shared-secret auth for the control plane (consolidation sprint 3.6).
//
// Before this, every /api route was unauthenticated: anyone with network
// access could start Opus pipelines, fire per-ticker thesis runs, delete
// stocks, and hit the DELETE endpoint that pkills host processes (audit §4.7).
//
// Opt-in: with SR_API_SECRET unset, behavior is unchanged (local dev).
// With it set, mutating /api requests (POST/PUT/PATCH/DELETE) require either
//   - header  x-sr-key: <secret>   (scripts / curl), or
//   - the sr_key cookie, enrolled once by visiting  /?sr_key=<secret>
//     (covers all 18 in-app fetch call sites with zero client changes).
//
// Honest limitation: a shared secret protects against drive-by LAN /
// port-forward abuse, not against an attacker who can read the operator's
// browser storage. Real multi-user auth is out of scope for a single-operator
// dashboard.

import { NextRequest, NextResponse } from "next/server";

const MUTATING = new Set(["POST", "PUT", "PATCH", "DELETE"]);
const COOKIE = "sr_key";

export function middleware(req: NextRequest) {
  const secret = process.env.SR_API_SECRET;
  if (!secret) return NextResponse.next();

  // One-time browser enrollment: /?sr_key=<secret> sets the cookie and
  // redirects to the same URL without the query param (keeps it out of
  // the address bar / history going forward).
  const offered = req.nextUrl.searchParams.get("sr_key");
  if (offered !== null) {
    const url = req.nextUrl.clone();
    url.searchParams.delete("sr_key");
    const res = NextResponse.redirect(url);
    if (offered === secret) {
      res.cookies.set(COOKIE, secret, {
        httpOnly: true,
        sameSite: "strict",
        path: "/",
      });
    }
    return res;
  }

  if (!req.nextUrl.pathname.startsWith("/api") || !MUTATING.has(req.method)) {
    return NextResponse.next();
  }

  const given = req.headers.get("x-sr-key") ?? req.cookies.get(COOKIE)?.value;
  if (given === secret) return NextResponse.next();

  return NextResponse.json(
    {
      error:
        "unauthorized: send header x-sr-key, or enroll this browser once via /?sr_key=<secret>",
    },
    { status: 401 },
  );
}

export const config = {
  // Pages (for enrollment) + all /api routes; skip static assets.
  matcher: ["/((?!_next/|favicon.ico).*)"],
};
