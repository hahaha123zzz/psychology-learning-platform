"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../lib/api";
import { listCourseReleases, type CourseRelease } from "../lib/course-api";
import {
  createTeachingAsset,
  listTeachingAssets,
  publishTeachingAsset,
  type TeachingAsset,
  type TeachingAssetTemplate,
} from "../lib/teaching-assets-api";

type Course = { id: string; title: string };
type DraftFields = {
  assetKey: string;
  template: TeachingAssetTemplate;
  title: string;
  text: string;
  items: string;
  fallbackText: string;
  evidenceRefs: string;
};

const EMPTY_DRAFT: DraftFields = {
  assetKey: "",
  template: "explanation",
  title: "",
  text: "",
  items: "",
  fallbackText: "",
  evidenceRefs: "",
};

const message = (reason: unknown) => reason instanceof ApiError ? reason.message : "资产工作区暂时无法读取。";

export default function TeachingAssetEditor() {
  const [courses, setCourses] = useState<Course[]>([]);
  const [courseId, setCourseId] = useState("");
  const [assets, setAssets] = useState<TeachingAsset[]>([]);
  const [releases, setReleases] = useState<CourseRelease[]>([]);
  const [draft, setDraft] = useState<DraftFields>(EMPTY_DRAFT);
  const [sourceAsset, setSourceAsset] = useState<TeachingAsset | null>(null);
  const [notice, setNotice] = useState("正在读取教学资产…");
  const [busy, setBusy] = useState(false);
  const loadSequence = useRef(0);

  const load = useCallback(async (id: string) => {
    if (!id) return;
    const sequence = ++loadSequence.current;
    try {
      const [nextAssets, nextReleases] = await Promise.all([listTeachingAssets(id), listCourseReleases(id)]);
      if (sequence !== loadSequence.current) return;
      setAssets(nextAssets);
      setReleases(nextReleases);
      setNotice("");
    } catch (reason) {
      if (sequence === loadSequence.current) setNotice(message(reason));
    }
  }, []);

  useEffect(() => {
    let active = true;
    api<Course[]>("/courses")
      .then((items) => {
        if (!active) return;
        setCourses(items);
        const first = items[0]?.id ?? "";
        setCourseId(first);
        if (first) void load(first);
        else setNotice("当前账号没有可编辑的课程。");
      })
      .catch((reason) => { if (active) setNotice(message(reason)); });
    return () => {
      active = false;
      loadSequence.current += 1;
    };
  }, [load]);

  function updateDraft<K extends keyof DraftFields>(key: K, value: DraftFields[K]) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  function selectCourse(id: string) {
    setCourseId(id);
    setAssets([]);
    setReleases([]);
    setDraft(EMPTY_DRAFT);
    setSourceAsset(null);
    void load(id);
  }

  function editAsNewVersion(asset: TeachingAsset) {
    const content = asset.content;
    setSourceAsset(asset);
    setDraft({
      assetKey: asset.asset_key,
      template: asset.template,
      title: typeof content.title === "string" ? content.title : "",
      text: typeof content.text === "string" ? content.text : "",
      items: Array.isArray(content.items)
        ? content.items.filter((item): item is string => typeof item === "string").join("\n")
        : "",
      fallbackText: asset.fallback_text,
      evidenceRefs: asset.evidence_refs.join(", "),
    });
    setNotice(`已载入 ${asset.asset_key} v${asset.version_no}；保存会新建后续草稿版本，原版本不会被覆盖。`);
  }

  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    if (!courseId) return;
    setBusy(true);
    try {
      const created = await createTeachingAsset(courseId, {
        asset_key: draft.assetKey.trim(),
        template: draft.template,
        content: {
          title: draft.title.trim(),
          text: draft.text.trim(),
          ...(draft.items.trim()
            ? { items: draft.items.split("\n").map((item) => item.trim()).filter(Boolean) }
            : {}),
        },
        fallback_text: draft.fallbackText.trim(),
        evidence_refs: draft.evidenceRefs.split(",").map((item) => item.trim()).filter(Boolean),
        allowed_actions: ["SHOW"],
      });
      formElement.reset();
      setDraft(EMPTY_DRAFT);
      setSourceAsset(null);
      setNotice(
        sourceAsset
          ? `已从 v${sourceAsset.version_no} 创建不可变草稿 v${created.version_no}；原版本保持不变。`
          : `教学资产草稿 v${created.version_no} 已保存；发布前不会出现在学生学习空间。`,
      );
      await load(courseId);
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function publish(asset: TeachingAsset) {
    const release = releases.find((item) => item.status === "published");
    if (!release) {
      setNotice("当前课程没有已发布版本，不能发布教学资产。");
      return;
    }
    setBusy(true);
    try {
      await publishTeachingAsset(courseId, asset, release.id);
      setNotice("教学资产已绑定已发布课程版本。学生只可读取该已发布资产版本。");
      await load(courseId);
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="functional-app" style={{ padding: "32px" }}>
      <p className="eyebrow">COURSE DESIGN · TEACHING ASSET</p>
      <h1>教学资产</h1>
      <p>资产使用固定字段、白名单模板和动作；新版本须绑定已发布课程版本后，学生才能读取。</p>
      {notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}

      <label className="field-label">
        当前课程
        <select value={courseId} onChange={(event) => selectCourse(event.target.value)} disabled={!courses.length}>
          {courses.map((course) => <option key={course.id} value={course.id}>{course.title}</option>)}
        </select>
      </label>

      <form className="support-form" onSubmit={(event) => void create(event)} aria-label="教学资产版本编辑器">
        <h2>{sourceAsset ? `编辑 ${sourceAsset.asset_key} v${sourceAsset.version_no} 的新版本` : "新建教学资产版本"}</h2>
        <p>已发布版本不可原地修改；保存会创建新的草稿版本并保留原版本。</p>
        <label className="field-label">资产 Key
          <input value={draft.assetKey} onChange={(event) => updateDraft("assetKey", event.target.value)} required pattern="[a-z0-9][a-z0-9._-]*" maxLength={100} placeholder="例如 attention-explanation" />
        </label>
        <label className="field-label">白名单模板
          <select value={draft.template} onChange={(event) => updateDraft("template", event.target.value as TeachingAssetTemplate)}>
            <option value="explanation">解释</option><option value="comparison">对比</option><option value="variable_map">变量映射</option><option value="table">表格</option><option value="focus">聚焦</option>
          </select>
        </label>
        <label className="field-label">标题
          <input value={draft.title} onChange={(event) => updateDraft("title", event.target.value)} required maxLength={160} />
        </label>
        <label className="field-label">正文（纯文本）
          <textarea value={draft.text} onChange={(event) => updateDraft("text", event.target.value)} maxLength={5000} rows={4} />
        </label>
        <label className="field-label">条目（每行一项，可选）
          <textarea value={draft.items} onChange={(event) => updateDraft("items", event.target.value)} rows={3} />
        </label>
        <label className="field-label">无障碍纯文本说明
          <textarea value={draft.fallbackText} onChange={(event) => updateDraft("fallbackText", event.target.value)} required maxLength={4000} rows={4} />
        </label>
        <label className="field-label">Evidence 引用（可选，逗号分隔）
          <input value={draft.evidenceRefs} onChange={(event) => updateDraft("evidenceRefs", event.target.value)} />
        </label>
        <section className="support-panel" aria-labelledby="asset-text-preview-title" aria-live="polite">
          <h3 id="asset-text-preview-title">无障碍文本预览</h3>
          <p>{draft.fallbackText.trim() || "填写纯文本说明后，学生可通过键盘与读屏访问该降级内容。"}</p>
        </section>
        <div className="attempt-actions">
          {sourceAsset && <button className="secondary-button" type="button" disabled={busy} onClick={() => { setSourceAsset(null); setDraft(EMPTY_DRAFT); setNotice("已取消新版本编辑。"); }}>取消编辑</button>}
          <button className="primary-button" disabled={busy || !courseId}>保存为新草稿版本</button>
        </div>
      </form>

      <section className="support-panel teacher-list">
        <div className="panel-heading"><h2>资产版本</h2><span>{assets.length} 个</span></div>
        {assets.length ? assets.map((asset) => (
          <article className="teacher-row" key={asset.id}>
            <div>
              <span className={`status-tag ${asset.status}`}>{asset.status}</span>
              <strong>{asset.asset_key} · v{asset.version_no}</strong>
              <small>{asset.template} · {asset.fallback_text}</small>
            </div>
            <div className="attempt-actions">
              <button className="secondary-button" type="button" disabled={busy} onClick={() => editAsNewVersion(asset)}>复制并编辑为新版本</button>
              {asset.status === "draft" && <button className="secondary-button" type="button" disabled={busy} onClick={() => void publish(asset)}>绑定已发布版本</button>}
            </div>
          </article>
        )) : <p className="empty-state">当前课程暂无教学资产。</p>}
      </section>
    </main>
  );
}
