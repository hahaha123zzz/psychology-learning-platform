"use client";

import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";
import { listCourseReleases, updateCourseRelease, type CourseRelease } from "../lib/course-api";

type Course = { id: string; title: string };
type PackKey = "domain_pack" | "pedagogy_pack" | "assessment_pack";

function describePackError(error: ApiError): string {
  if (!error.details || typeof error.details !== "object") return error.message;
  if (Array.isArray(error.details)) {
    const fields = error.details.flatMap((item) => {
      if (typeof item !== "object" || item === null) return [];
      const entry = item as { loc?: unknown; msg?: unknown };
      const path = Array.isArray(entry.loc)
        ? entry.loc
            .filter((part): part is string | number => typeof part === "string" || typeof part === "number")
            .join(".")
        : "";
      return typeof entry.msg === "string" ? [`${path ? `${path}：` : ""}${entry.msg}`] : [];
    });
    return fields.length ? `${error.message} ${fields.slice(0, 5).join("；")}` : error.message;
  }
  const details = error.details as { field?: unknown; index?: unknown; unknown_fields?: unknown };
  if (Array.isArray(details.unknown_fields)) {
    const path = typeof details.index === "number" ? `${String(details.field)}[${details.index}]` : String(details.field ?? "Pack");
    return `${error.message} 位置：${path}；未定义字段：${details.unknown_fields.filter((field): field is string => typeof field === "string").join("、")}`;
  }
  if (typeof details.field === "string") {
    const path = typeof details.index === "number" ? `${details.field}[${details.index}]` : details.field;
    return `${error.message} 位置：${path}`;
  }
  return error.message;
}

export default function CourseDesignPackEditor({ pack, title, description }: { pack: PackKey; title: string; description: string }) {
  const [courses, setCourses] = useState<Course[]>([]); const [courseId, setCourseId] = useState(""); const [releases, setReleases] = useState<CourseRelease[]>([]); const [releaseId, setReleaseId] = useState(""); const [value, setValue] = useState("{}"); const [version, setVersion] = useState(1); const [notice, setNotice] = useState("正在读取课程设计草稿…"); const [busy, setBusy] = useState(false); const [versionConflict, setVersionConflict] = useState(false);
  const loadReleases = useCallback(async (id: string) => { if (!id) return; const next = await listCourseReleases(id); setReleases(next); const draft = next.find((item) => item.status === "draft"); setVersionConflict(false); if (draft) { setReleaseId(draft.id); setVersion(draft.version); setValue(JSON.stringify(draft.manifest[pack] ?? {}, null, 2)); setNotice(""); } else { setReleaseId(""); setNotice("当前课程没有可编辑的发布草稿，请先在发布页创建版本。"); } }, [pack]);
  useEffect(() => { api<Course[]>("/courses").then((items) => { setCourses(items); const id = items[0]?.id ?? ""; setCourseId(id); return id ? loadReleases(id) : undefined; }).catch((reason) => setNotice(reason instanceof Error ? reason.message : "课程读取失败。")); }, [loadReleases]);
  async function save() { if (!courseId || !releaseId) return; let parsed: Record<string, unknown>; try { const candidate = JSON.parse(value) as unknown; if (!candidate || typeof candidate !== "object" || Array.isArray(candidate)) throw new Error("Pack 必须是 JSON 对象"); parsed = candidate as Record<string, unknown>; } catch (error) { setNotice(error instanceof Error ? error.message : "JSON 格式不正确。"); return; } setBusy(true); setVersionConflict(false); try { const next = await updateCourseRelease(courseId, releaseId, { version, [pack]: parsed }); setVersion(next.version); setNotice("设计草稿已保存；发布前仍需通过服务端门禁。"); } catch (error) { if (error instanceof ApiError && error.status === 409) { setVersionConflict(true); setNotice(`${error.message} 本地内容尚未丢弃，可选择重新载入服务端草稿。`); } else if (error instanceof ApiError && typeof error.details === "object" && error.details !== null && "issues" in error.details && Array.isArray(error.details.issues)) { const details = error.details.issues.map((issue) => { if (typeof issue !== "object" || issue === null) return ""; const item = issue as { path?: unknown; message?: unknown }; return [item.path, item.message].filter((part): part is string => typeof part === "string").join("："); }).filter(Boolean); setNotice(details.length ? `${error.message} ${details.join("；")}` : error.message); } else if (error instanceof ApiError) { setNotice(describePackError(error)); } else { setNotice(error instanceof Error ? error.message : "保存失败，请刷新后重试。"); } } finally { setBusy(false); } }
  return <main className="functional-app" style={{ padding: "32px" }}><p className="eyebrow">COURSE DESIGN</p><h1>{title}</h1><p>{description}</p>{notice && <p className="status-banner" role="status">{notice}{versionConflict && <button className="secondary-button" disabled={busy} onClick={() => void loadReleases(courseId)}>重新载入服务端草稿（放弃本地编辑）</button>}</p>}<label className="field-label">当前课程<select value={courseId} onChange={(event) => { setCourseId(event.target.value); void loadReleases(event.target.value); }}>{courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}</select></label>{releases.length > 0 && <p className="empty-state">当前草稿：{releases.find((item) => item.id === releaseId)?.name ?? "—"} · 版本 {version}</p>}{pack === "domain_pack" && <details className="domain-experiment-help"><summary>ExperimentSchema 字段说明</summary><p>按教材证据如实填写；教材未提供的信息请省略或留空，不让模型补成课程事实。每个实验仍需通过对应 EvidenceBinding 绑定到教材版本和来源对象。</p><p><strong>字段：</strong>research_question、hypothesis、iv、dv、operationalization、controls、confounds、design、procedure、prediction、result_pattern、interpretation、limitations。controls/confounds 使用字符串数组，其余为文本。</p><p><strong>教材证据：</strong>textbook_evidence 填 EvidenceBinding 稳定 key 数组，可与 evidence_binding_keys 等价使用；若两个字段同时填写，必须一致。</p></details>}<textarea className="design-pack-editor" value={value} onChange={(event) => setValue(event.target.value)} aria-label={`${title} JSON`} spellCheck={false} disabled={!releaseId} /><button className="primary-button" disabled={busy || !releaseId} onClick={() => void save()}>{busy ? "保存中…" : "保存设计草稿"}</button></main>;
}
