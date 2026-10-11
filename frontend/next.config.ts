import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  async rewrites() {
    // `rewrites` is evaluated while `next build` runs.  In the production
    // container that must resolve through Docker DNS, not the frontend's own
    // loopback interface. Local `next dev` keeps the host API default.
    const backend = process.env.BACKEND_URL ?? (
      process.env.NODE_ENV === "production" ? "http://nginx" : "http://localhost:8000"
    );
    return [{ source: "/api/:path*", destination: `${backend}/:path*` }];
  },
  /* config options here */
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
