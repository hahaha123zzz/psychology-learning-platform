import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

export default defineConfig([
  ...nextVitals,
  ...nextTs,
  globalIgnores([
    ".next/**",
    ".next-r2-*/**",
    ".next-r3-*/**",
    ".r2-runtime/**",
    ".r3-runtime/**",
    "out/**",
    "tmp/**",
    "next-env.d.ts",
  ]),
]);
