export type NextRuntimeEnvironment = Readonly<Record<string, string | undefined>>;

export interface NextRuntimeConfig {
  apiProxyOrigin: string;
  distDir: string;
}

export declare function resolveNextRuntimeConfig(
  environment?: NextRuntimeEnvironment,
): NextRuntimeConfig;
