"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { api } from "../../../lib/api";
import { listCourseReleases, type CourseRelease } from "../../../lib/course-api";

type Course = { id: string; title: string };
type ManifestChange = {
  path: string;
  kind: "added" | "removed" | "changed";
  before?: unknown;
  after?: unknown;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getManifestChanges(before: unknown, after: unknown): ManifestChange[] {
  const changes: ManifestChange[] = [];
  const visit = (left: unknown, right: unknown, path: string) => {
    if (isRecord(left) && isRecord(right)) {
      const keys = [...new Set([...Object.keys(left), ...Object.keys(right)])].sort();
      for (const key of keys) {
        const childPath = path + "." + key;
        const hasLeft = Object.prototype.hasOwnProperty.call(left, key);
        const hasRight = Object.prototype.hasOwnProperty.call(right, key);
        if (!hasLeft) changes.push({ path: childPath, kind: "added", after: right[key] });
        else if (!hasRight) changes.push({ path: childPath, kind: "removed", before: left[key] });
        else visit(left[key], right[key], childPath);
      }
      return;
    }
    if (Array.isArray(left) && Array.isArray(right)) {
      const length = Math.max(left.length, right.length);
      for (let index = 0; index < length; index += 1) {
        const childPath = path + "[" + index + "]";
        if (index >= left.length) changes.push({ path: childPath, kind: "added", after: right[index] });
        else if (index >= right.length) changes.push({ path: childPath, kind: "removed", before: left[index] });
        else visit(left[index], right[index], childPath);
      }
      return;
    }
    if (!Object.is(left, right)) changes.push({ path, kind: "changed", before: left, after: right });
  };

  visit(before, after, "manifest");
  return changes;
}

function prettyValue(value: unknown): string {
  if (value === undefined) return "—";
  return JSON.stringify(value, null, 2) ?? "—";
}

function changeLabel(kind: ManifestChange["kind"]): string {
  if (kind === "added") return "新增";
  if (kind === "removed") return "删除";
  return "修改";
}

export default function CourseDesignReleasesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [releases, setReleases] = useState<CourseRelease[]>([]);
  const [previewId, setPreviewId] = useState("");
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [courseLoading, setCourseLoading] = useState(true);
  const [courseError, setCourseError] = useState("");
  const [releaseLoading, setReleaseLoading] = useState(false);
  const [releaseError, setReleaseError] = useState("");
  const releaseRequest = useRef(0);

  const loadReleases = useCallback(async (id: string) => {
    const request = ++releaseRequest.current;
    setReleases([]);
    setPreviewId("");
    setBeforeId("");
    setAfterId("");
    setReleaseError("");
    if (!id) {
      setReleaseLoading(false);
      return;
    }

    setReleaseLoading(true);
    try {
      const items = await listCourseReleases(id);
      if (request !== releaseRequest.current) return;
      const ordered = [...items].sort((a, b) => b.version_no - a.version_no || a.id.localeCompare(b.id));
      setReleases(ordered);
      setPreviewId(ordered[0]?.id ?? "");
      setBeforeId(ordered[1]?.id ?? "");
      setAfterId(ordered[0]?.id ?? "");
    } catch (error) {
      if (request !== releaseRequest.current) return;
      setReleaseError(error instanceof Error ? error.message : "课程版本读取失败。");
    } finally {
      if (request === releaseRequest.current) setReleaseLoading(false);
    }
  }, []);

  const loadCourses = useCallback(async () => {
    setCourseLoading(true);
    setCourseError("");
    try {
      const items = await api<Course[]>("/courses");
      setCourses(items);
      const nextId = items[0]?.id ?? "";
      setCourseId(nextId);
      await loadReleases(nextId);
    } catch (error) {
      setCourseError(error instanceof Error ? error.message : "课程读取失败。");
    } finally {
      setCourseLoading(false);
    }
  }, [loadReleases]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => {
      if (active) void loadCourses();
    });
    return () => {
      active = false;
      releaseRequest.current += 1;
    };
  }, [loadCourses]);

  const orderedReleases = useMemo(
    () => [...releases].sort((a, b) => b.version_no - a.version_no || a.id.localeCompare(b.id)),
    [releases],
  );
  const previewRelease = orderedReleases.find((release) => release.id === previewId);
  const beforeRelease = orderedReleases.find((release) => release.id === beforeId);
  const afterRelease = orderedReleases.find((release) => release.id === afterId);
  const changes = useMemo(
    () => beforeRelease && afterRelease && beforeRelease.id !== afterRelease.id
      ? getManifestChanges(beforeRelease.manifest, afterRelease.manifest)
      : [],
    [beforeRelease, afterRelease],
  );

  function selectCourse(id: string) {
    setCourseId(id);
    void loadReleases(id);
  }

  return (
    <main className="functional-app" style={{ padding: "32px" }}>
      <p className="eyebrow">COURSE RELEASE</p>
      <h1>版本预览与差异</h1>
      <p>查看服务端返回的课程 Release manifest，并比较已加载版本的内容变化。</p>
      <p className="status-banner" role="note">内容差异仅供核对，不是发布门禁；本页不会创建、保存或发布版本。</p>

      {courseLoading ? <p className="status-banner" role="status">正在读取课程…</p> : null}
      {courseError ? (
        <p className="status-banner" role="alert">
          {courseError} <button className="secondary-button" onClick={() => void loadCourses()}>重试读取</button>
        </p>
      ) : null}

      {!courseLoading && !courseError && courses.length === 0 ? (
        <p className="empty-state">当前账号没有可查看的课程。</p>
      ) : null}

      {!courseLoading && !courseError && courses.length > 0 ? (
        <>
          <label className="field-label">
            当前课程
            <select value={courseId} onChange={(event) => selectCourse(event.target.value)}>
              {courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
            </select>
          </label>

          <section className="data-panel" aria-labelledby="release-list-heading">
            <h2 id="release-list-heading">课程版本</h2>
            {releaseLoading ? <p className="status-banner" role="status">正在读取版本…</p> : null}
            {releaseError ? (
              <p className="status-banner" role="alert">
                {releaseError} <button className="secondary-button" onClick={() => void loadReleases(courseId)}>重试读取</button>
              </p>
            ) : null}
            {!releaseLoading && !releaseError && orderedReleases.length === 0 ? (
              <p className="empty-state">当前课程暂无可查看的版本。</p>
            ) : null}
            {orderedReleases.map((release) => (
              <div className="mini-row" key={release.id}>
                <span>
                  <strong>v{release.version_no} · {release.name}</strong>
                  <small>{release.status} · 教材 {release.manifest.materials.length} 项</small>
                </span>
                <button className="secondary-button" onClick={() => setPreviewId(release.id)}>查看 manifest</button>
              </div>
            ))}
          </section>

          {previewRelease ? (
            <section className="data-panel" aria-labelledby="manifest-preview-heading">
              <h2 id="manifest-preview-heading">Manifest 预览</h2>
              <label className="field-label">
                选择版本
                <select value={previewId} onChange={(event) => setPreviewId(event.target.value)}>
                  {orderedReleases.map((release) => (
                    <option key={release.id} value={release.id}>v{release.version_no} · {release.name} · {release.status}</option>
                  ))}
                </select>
              </label>
              <pre aria-label="真实课程 Release manifest">{JSON.stringify(previewRelease.manifest, null, 2)}</pre>
            </section>
          ) : null}

          <section className="data-panel" aria-labelledby="manifest-diff-heading">
            <h2 id="manifest-diff-heading">版本内容差异</h2>
            <p className="empty-state">下方只比较两个版本的 manifest 字段，不代表官方 Review 或发布 Gate。</p>
            {orderedReleases.length < 2 ? <p className="empty-state">至少需要两个真实课程版本才能比较。</p> : (
              <>
                <div className="inline-form">
                  <label className="field-label">
                    对比版本
                    <select value={beforeId} onChange={(event) => setBeforeId(event.target.value)}>
                      {orderedReleases.map((release) => (
                        <option key={release.id} value={release.id}>v{release.version_no} · {release.name}</option>
                      ))}
                    </select>
                  </label>
                  <span aria-hidden="true">→</span>
                  <label className="field-label">
                    目标版本
                    <select value={afterId} onChange={(event) => setAfterId(event.target.value)}>
                      {orderedReleases.map((release) => (
                        <option key={release.id} value={release.id}>v{release.version_no} · {release.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
                {beforeId === afterId ? <p className="empty-state">请选择两个不同版本。</p> : null}
                {beforeId !== afterId && changes.length === 0 ? <p className="empty-state">这两个 manifest 没有字段差异。</p> : null}
                {changes.length > 0 ? (
                  <div style={{ overflowX: "auto" }}>
                    <table>
                      <thead><tr><th>字段路径</th><th>变化</th><th>原值</th><th>新值</th></tr></thead>
                      <tbody>
                        {changes.map((change) => (
                          <tr key={change.path}>
                            <th scope="row">{change.path}</th>
                            <td>{changeLabel(change.kind)}</td>
                            <td><pre>{prettyValue(change.before)}</pre></td>
                            <td><pre>{prettyValue(change.after)}</pre></td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </>
            )}
          </section>
        </>
      ) : null}
    </main>
  );
}
