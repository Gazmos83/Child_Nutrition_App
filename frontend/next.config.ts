import type { NextConfig } from "next";

// The browser talks to one origin; /api/* is proxied to FastAPI (design.md Decision 9).
const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${backendUrl}/api/:path*` }];
  },
};

export default nextConfig;
