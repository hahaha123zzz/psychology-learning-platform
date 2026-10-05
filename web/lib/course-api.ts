import { api } from "./api";

export type CourseClass = {
  id: string;
  course_id: string;
  code: string;
  name: string;
  status: "active" | "archived";
  version: number;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type TeacherAssignment = {
  id: string;
  class_id: string;
  teacher_id: string;
  teacher_name: string;
  assignment_role: "lead" | "assistant";
  status: "active" | "ended";
  version: number;
  assigned_by: string;
  created_at: string;
};

export type CourseRelease = {
  id: string;
  course_id: string;
  version_no: number;
  name: string;
  status: "draft" | "published" | "deprecated";
  manifest: {
    schema_version: "course-release.v1";
    materials: string[];
    domain_pack?: Record<string, unknown>;
    pedagogy_pack?: Record<string, unknown>;
    assessment_pack?: Record<string, unknown>;
  };
  version: number;
  created_by: string;
  published_by: string | null;
  published_at: string | null;
  deprecated_at: string | null;
  created_at: string;
  updated_at: string;
};

export function listCourseClasses(courseId: string) {
  return api<CourseClass[]>(`/courses/${courseId}/classes`);
}

export function createCourseClass(courseId: string, input: { code: string; name: string }) {
  return api<CourseClass>(`/courses/${courseId}/classes`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listClassTeachers(courseId: string, classId: string) {
  return api<TeacherAssignment[]>(`/courses/${courseId}/classes/${classId}/teachers`);
}

export function assignClassTeacher(
  courseId: string,
  classId: string,
  input: { teacher_id: string; assignment_role?: TeacherAssignment["assignment_role"] },
) {
  return api<TeacherAssignment>(`/courses/${courseId}/classes/${classId}/teachers`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function listCourseReleases(courseId: string) {
  return api<CourseRelease[]>(`/courses/${courseId}/releases`);
}

export function createCourseRelease(
  courseId: string,
  input: {
    name: string;
    material_ids?: string[];
    domain_pack?: Record<string, unknown>;
    pedagogy_pack?: Record<string, unknown>;
    assessment_pack?: Record<string, unknown>;
  },
) {
  return api<CourseRelease>(`/courses/${courseId}/releases`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function updateCourseRelease(
  courseId: string,
  releaseId: string,
  input: {
    version: number;
    name?: string;
    material_ids?: string[];
    domain_pack?: Record<string, unknown>;
    pedagogy_pack?: Record<string, unknown>;
    assessment_pack?: Record<string, unknown>;
  },
) {
  return api<CourseRelease>(`/courses/${courseId}/releases/${releaseId}`, {
    method: "PATCH",
    body: JSON.stringify(input),
  });
}

export async function publishCourseRelease(courseId: string, releaseId: string) {
  const releases = await listCourseReleases(courseId);
  const release = releases.find((item) => item.id === releaseId);
  if (!release || release.status !== "draft") {
    throw new Error("当前课程草稿不存在或已不能发布，请刷新后重试。");
  }
  return api<CourseRelease>(`/courses/${courseId}/releases/${releaseId}/publish`, {
    method: "POST",
    headers: { "Idempotency-Key": `release-publish:${releaseId}:${release.version}` },
    body: JSON.stringify({ expected_version: release.version }),
  });
}
