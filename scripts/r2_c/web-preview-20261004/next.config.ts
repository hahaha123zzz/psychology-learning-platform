import type { NextConfig } from "next";
import { resolveNextRuntimeConfig } from "./lib/next-runtime-config.mjs";

const runtimeConfig = resolveNextRuntimeConfig();

const nextConfig: NextConfig = {
  output: "standalone",
  distDir: runtimeConfig.distDir,
  poweredByHeader: false,
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${runtimeConfig.apiProxyOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
