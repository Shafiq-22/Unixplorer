import type { NextConfig } from "next";

const apiUrl = process.env.ATLAS_API_URL ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@atlas/shared-types"],
  // Same-origin proxy: the browser calls /api/*, the Next server forwards to FastAPI.
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${apiUrl}/:path*` }];
  },
};

export default config;
