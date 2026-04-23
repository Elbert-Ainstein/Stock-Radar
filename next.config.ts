import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Allow cross-origin access to /_next/* dev resources from LAN / tunnel hosts.
  // The dev server is bound to 0.0.0.0, so HMR can be hit from any IP on the
  // network — listing them here silences Next's safety warning.
  allowedDevOrigins: [
    "100.108.58.53",
    "localhost",
    "127.0.0.1",
    // Common private LAN ranges — add more IPs here if you access the dev
    // server from other devices.
  ],
};

export default nextConfig;
