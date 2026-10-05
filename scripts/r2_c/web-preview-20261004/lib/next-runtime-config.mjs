const DEFAULT_API_PROXY_TARGET = "http://127.0.0.1:8000";
const DEFAULT_NEXT_DIST_DIR = ".next";
const ALLOWED_NEXT_DIST_DIRS = new Set([
  DEFAULT_NEXT_DIST_DIR,
  ".next-r2-root",
  ".next-r2-a",
  ".next-r2-b",
  ".next-r2-c",
]);

/**
 * 解析 Next.js 的窗口隔离配置。
 * distDir 限定为项目根目录下的单层目录，防止环境变量把构建产物写出工作区。
 * @param {Readonly<Record<string, string | undefined>>} [environment]
 */
export function resolveNextRuntimeConfig(environment = process.env) {
  const targetValue = environment.PSYCHOLOGY_API_PROXY_TARGET?.trim() || DEFAULT_API_PROXY_TARGET;
  let target;
  try {
    target = new URL(targetValue);
  } catch {
    throw new TypeError("PSYCHOLOGY_API_PROXY_TARGET 必须是 HTTP(S) origin。");
  }

  if (
    !["http:", "https:"].includes(target.protocol) ||
    target.username ||
    target.password ||
    (target.pathname !== "" && target.pathname !== "/") ||
    target.search ||
    target.hash
  ) {
    throw new TypeError("PSYCHOLOGY_API_PROXY_TARGET 只能包含无凭据的 HTTP(S) origin。");
  }

  const distDir = environment.PSYCHOLOGY_NEXT_DIST_DIR?.trim() || DEFAULT_NEXT_DIST_DIR;
  if (!ALLOWED_NEXT_DIST_DIRS.has(distDir)) {
    throw new TypeError("PSYCHOLOGY_NEXT_DIST_DIR 必须是已登记的独立窗口构建目录。");
  }

  return {
    apiProxyOrigin: target.origin,
    distDir,
  };
}
