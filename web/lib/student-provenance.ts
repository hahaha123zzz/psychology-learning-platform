export type StudentProvenanceStatus = "unreviewed" | "verified" | "rejected";
export type StudentCourseResourceRole = "course_textbook" | "supplementary_resource";

export type StudentProvenance = {
  source_title: string | null;
  publisher: string | null;
  content_author: string | null;
  edition: string | null;
  source_url: string | null;
  license: string | null;
  course_resource_role: StudentCourseResourceRole | null;
  status: StudentProvenanceStatus;
  version: number;
};

function nullableText(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

export function readStudentProvenance(value: unknown): StudentProvenance | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const source = value as Record<string, unknown>;
  const status = source.status;
  const version = source.version;
  if (
    (status !== "unreviewed" && status !== "verified" && status !== "rejected") ||
    typeof version !== "number" || !Number.isInteger(version) || version < 1
  ) return null;

  const role = source.course_resource_role;
  return {
    source_title: nullableText(source.source_title),
    publisher: nullableText(source.publisher),
    content_author: nullableText(source.content_author),
    edition: nullableText(source.edition),
    source_url: nullableText(source.source_url),
    license: nullableText(source.license),
    course_resource_role: role === "course_textbook" || role === "supplementary_resource" ? role : null,
    status,
    version,
  };
}

export function studentProvenanceStatusLabel(status: StudentProvenanceStatus | null): string {
  if (status === "verified") return "课程已审核来源信息";
  if (status === "rejected") return "课程审核未通过";
  if (status === "unreviewed") return "来源信息待课程审核";
  return "来源信息未提供";
}

export function studentCourseResourceRoleLabel(role: StudentCourseResourceRole | null): string {
  if (role === "course_textbook") return "课程教材用途";
  if (role === "supplementary_resource") return "补充课程资料";
  return "课程用途未分类";
}
