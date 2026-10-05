import { api, ApiError } from "./api";

type UnknownRecord = Record<string, unknown>;

export type AdminGovernanceOverview = {
  apiStatus: "ok" | "degraded";
  databaseStatus: string;
  redisStatus: string;
  organizationUserCount: number;
  inProgressAttempts: number;
  serverTime: string;
};

function asRecord(value: unknown): UnknownRecord | null {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as UnknownRecord
    : null;
}

function finiteCount(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : 0;
}

function safeStatus(value: unknown): string {
  return typeof value === "string" && value.length <= 40 ? value : "unknown";
}

export async function loadAdminGovernanceOverview(): Promise<AdminGovernanceOverview> {
  const [readyResponse, adminData] = await Promise.all([
    fetch("/api/v1/health/ready", { credentials: "include", cache: "no-store" }),
    api<unknown>("/admin/health", { cache: "no-store" }),
  ]);
  const readyBody = asRecord(await readyResponse.json().catch(() => null));
  if (!readyBody) {
    throw new ApiError(readyResponse.status, "无法读取服务就绪状态，请稍后重试。", undefined, "ADMIN_READINESS_UNAVAILABLE", true);
  }

  const admin = asRecord(adminData);
  if (!admin) {
    throw new ApiError(502, "管理员运行概览返回格式无效，请刷新后重试。", undefined, "ADMIN_OVERVIEW_INVALID");
  }
  const checks = asRecord(readyBody.checks);
  const counts = asRecord(admin.counts);
  const healthStatus = readyBody.status === "ok" && readyResponse.ok ? "ok" : "degraded";

  return {
    apiStatus: healthStatus,
    databaseStatus: safeStatus(checks?.database ?? admin.database),
    redisStatus: safeStatus(checks?.redis),
    organizationUserCount: finiteCount(counts?.users),
    inProgressAttempts: finiteCount(admin.attempts_in_progress),
    serverTime: typeof readyBody.time === "string"
      ? readyBody.time
      : typeof admin.server_time === "string" ? admin.server_time : "",
  };
}
