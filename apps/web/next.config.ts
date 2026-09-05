import type { NextConfig } from "next";

const API_URL = process.env.BEARCASE_API_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
  async redirects() {
    return [{ source: "/github", destination: process.env.NEXT_PUBLIC_GITHUB_URL ?? "https://github.com", permanent: false }];
  },
};

export default nextConfig;
