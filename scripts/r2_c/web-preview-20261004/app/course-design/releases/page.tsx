"use client";

import { FormEvent, useEffect, useState } from "react";

import { api } from "../../../lib/api";
import {
  createCourseRelease,
  listCourseReleases,
  publishCourseRelease,
  type CourseRelease,
} from "../../../lib/course-api";

type Course = { id: string; title: string };

export default function CourseDesignReleasesPage() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [releases, setReleases] = useState<CourseRelease[]>([]);
  const [name, setName] = useState("");
  const [domainPack, setDomainPack] = useState("{}");
  const [pedagogyPack, setPedagogyPack] = useState("{}");
  const [assessmentPack, setAssessmentPack] = useState("{}");
  const [notice, setNotice] = useState("正在读取课程版本…");
  const [busy, setBusy] = useState(false);

  async function loadReleases(id: string) {
    if (!id) return;
    try {
      setReleases(await listCourseReleases(id));
      setNotice("");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "课程版本读取失败。");
    }
  }

  useEffect(() => {
    void api<Course[]>("/courses")
      .then((items) => {
        setCourses(items);
        const nextId = items[0]?.id ?? "";
        setCourseId(nextId);
        return nextId ? loadReleases(nextId) : undefined;
      })
      .catch((error) => setNotice(error instanceof Error ? error.message : "课程读取失败。"));
  }, []);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!courseId || !name.trim()) return;
    setBusy(true);
    try {
      const parsePack = (value: string) => {
        const parsed = JSON.parse(value) as unknown;
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) throw new Error("Pack 必须是 JSON 对象");
        return parsed as Record<string, unknown>;
      };
      await createCourseRelease(courseId, {
        name: name.trim(),
        material_ids: [],
        domain_pack: parsePack(domainPack),
        pedagogy_pack: parsePack(pedagogyPack),
        assessment_pack: parsePack(assessmentPack),
      });
      setName("");
      await loadReleases(courseId);
      setNotice("课程版本草稿已创建；发布前仍需完成领域、教学和测评门禁。 ");
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "课程版本创建失败。");
    } finally {
      setBusy(false);
    }
  }

  async function publish(release: CourseRelease) {
    if (!courseId || release.status !== "draft") return;
    setBusy(true);
    try {
      await publishCourseRelease(courseId, release.id);
      await loadReleases(courseId);
      setNotice(`版本 ${release.version_no} 已发布，旧版本不会被原地修改。`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : "课程版本发布失败。");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="functional-app" style={{ padding: "32px" }}>
      <p className="eyebrow">COURSE RELEASE</p>
      <h1>发布</h1>
      <p>课程版本由服务端固定 manifest；发布前必须通过教材和资产门禁。</p>
      {notice && <p className="status-banner">{notice}</p>}
      {courses.length > 0 ? (
        <>
          <label className="field-label">
            当前课程
            <select value={courseId} onChange={(event) => { setCourseId(event.target.value); void loadReleases(event.target.value); }}>
              {courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
            </select>
          </label>
          <form className="inline-form" onSubmit={create}>
            <input value={name} onChange={(event) => setName(event.target.value)} placeholder="新版本名称" required />
            <textarea value={domainPack} onChange={(event) => setDomainPack(event.target.value)} placeholder='Domain Pack JSON，例如 {"chapters":[]}' aria-label="Domain Pack" />
            <textarea value={pedagogyPack} onChange={(event) => setPedagogyPack(event.target.value)} placeholder='Pedagogy Pack JSON，例如 {"tasks":[]}' aria-label="Pedagogy Pack" />
            <textarea value={assessmentPack} onChange={(event) => setAssessmentPack(event.target.value)} placeholder='Assessment Pack JSON，例如 {"release_ids":[]}' aria-label="Assessment Pack" />
            <button className="primary-button" disabled={busy || !courseId}>创建草稿</button>
          </form>
          <section className="data-panel">
            <h2>课程版本</h2>
            {releases.length === 0 ? <p className="empty-state">暂无课程版本草稿。</p> : releases.map((release) => (
              <div className="mini-row" key={release.id}>
                <span><strong>v{release.version_no} · {release.name}</strong><small>{release.status} · 教材 {release.manifest.materials.length} 项</small></span>
                {release.status === "draft" && <button className="secondary-button" disabled={busy} onClick={() => void publish(release)}>发布</button>}
              </div>
            ))}
          </section>
        </>
      ) : <p className="empty-state">当前账号没有可管理的课程，无法创建发布版本。</p>}
    </main>
  );
}
