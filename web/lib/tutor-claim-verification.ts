export type TutorClaimStatus = "supported" | "partially-supported" | "contradicted" | "unknown";

export type TutorClaimRefusalReason =
  | "counterevidence_unverified"
  | "retrieval_scope_changed"
  | "insufficient_evidence"
  | "claim_partially_supported"
  | "claim_contradicted"
  | "learning_evidence_cannot_support_content_claim"
  | "claim_verification_timeout"
  | "claim_verification_failed"
  | "release_material_versions_unpinned"
  | "release_domain_snapshot_missing"
  | "domain_release_unavailable"
  | "release_material_snapshots_unpinned"
  | "release_material_snapshots_mismatch"
  | "publication_snapshot_unavailable"
  | "publication_index_job_mismatch"
  | "publication_retrieval_snapshot_missing";

export type TutorClaimVerificationSummary = {
  status: TutorClaimStatus;
  refusal_reason: TutorClaimRefusalReason | null;
  supplemental_retrieval_attempts: 0 | 1;
};

const CLAIM_STATUS_LABELS: Record<TutorClaimStatus, string> = {
  supported: "证据支持",
  "partially-supported": "部分支持",
  contradicted: "发现反证",
  unknown: "暂无法确认",
};

const CLAIM_REFUSAL_LABELS: Record<TutorClaimRefusalReason, string> = {
  counterevidence_unverified: "反向线索尚未核验。",
  retrieval_scope_changed: "检索范围已变化，当前结果不作确定结论。",
  insufficient_evidence: "当前证据不足以确认。",
  claim_partially_supported: "证据只支持其中一部分。",
  claim_contradicted: "发现与该主张不一致的证据。",
  learning_evidence_cannot_support_content_claim: "学习记录不能替代课程内容证据。",
  claim_verification_timeout: "核对过程未完成。",
  claim_verification_failed: "核对过程未完成。",
  release_material_versions_unpinned: "课程资料版本未能确认。",
  release_domain_snapshot_missing: "课程知识范围未能确认。",
  domain_release_unavailable: "课程知识范围未能确认。",
  release_material_snapshots_unpinned: "课程资料快照未能完整确认。",
  release_material_snapshots_mismatch: "课程资料快照未能完整确认。",
  publication_snapshot_unavailable: "课程资料快照未能完整确认。",
  publication_index_job_mismatch: "课程资料快照未能完整确认。",
  publication_retrieval_snapshot_missing: "课程资料快照未能完整确认。",
};

const CLAIM_STATUSES = new Set<string>(Object.keys(CLAIM_STATUS_LABELS));
const CLAIM_REFUSAL_REASONS = new Set<string>(Object.keys(CLAIM_REFUSAL_LABELS));

export function readTutorClaimVerification(value: unknown): TutorClaimVerificationSummary | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const candidate = value as Record<string, unknown>;
  if (!CLAIM_STATUSES.has(String(candidate.status))) return null;
  if (typeof candidate.supplemental_retrieval_attempts !== "number" ||
      !Number.isInteger(candidate.supplemental_retrieval_attempts) ||
      (candidate.supplemental_retrieval_attempts !== 0 && candidate.supplemental_retrieval_attempts !== 1)) return null;
  const refusalReason = candidate.refusal_reason;
  if (refusalReason !== null && (typeof refusalReason !== "string" || !CLAIM_REFUSAL_REASONS.has(refusalReason))) return null;
  return {
    status: candidate.status as TutorClaimStatus,
    refusal_reason: refusalReason as TutorClaimRefusalReason | null,
    supplemental_retrieval_attempts: candidate.supplemental_retrieval_attempts as 0 | 1,
  };
}

export function tutorClaimStatusLabel(status: TutorClaimStatus): string {
  return CLAIM_STATUS_LABELS[status];
}

export function tutorClaimRefusalLabel(reason: TutorClaimRefusalReason | null): string | null {
  return reason ? CLAIM_REFUSAL_LABELS[reason] : null;
}

export function formatTutorClaimVerification(summary: TutorClaimVerificationSummary): string {
  const refusalLabel = tutorClaimRefusalLabel(summary.refusal_reason);
  return [
    tutorClaimStatusLabel(summary.status),
    `补充检索次数：${summary.supplemental_retrieval_attempts}`,
    refusalLabel,
  ].filter(Boolean).join(" · ");
}
