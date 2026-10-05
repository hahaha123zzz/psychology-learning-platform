"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { ApiError, api } from "../lib/api";

type Preferences = {
  user_id: string;
  preferences: {
    hint_density: "standard" | "compact" | "guided";
    reduced_motion: boolean;
    font_scale: "100" | "115" | "130";
    notification_in_app: boolean;
    response_length: "CONCISE" | "BALANCED" | "DETAILED";
    example_order: "EXAMPLE_FIRST" | "CONCEPT_FIRST" | "ADAPTIVE";
  };
  version: number;
};

const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "偏好保存失败。";

export default function StudentPreferencesPanel() {
  const [data, setData] = useState<Preferences | null>(null);
  const [notice, setNotice] = useState("正在读取偏好…");
  const [saving, setSaving] = useState(false);
  const dirtyFields = useRef(new Set<keyof Preferences["preferences"]>());
  useEffect(() => { api<Preferences>("/me/preferences").then((next) => { setData(next); setNotice(""); }).catch((reason) => setNotice(explain(reason))); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || saving) return;
    setSaving(true);
    setNotice("");
    const draft = data.preferences;
    try {
      const next = await api<Preferences>("/me/preferences", { method: "PATCH", body: JSON.stringify({ version: data.version, ...draft }) });
      setData(next);
      dirtyFields.current.clear();
      setNotice("偏好已保存。");
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "RESOURCE_VERSION_CONFLICT") {
        try {
          const latest = await api<Preferences>("/me/preferences");
          const rebased = { ...latest.preferences };
          for (const key of dirtyFields.current) rebased[key] = draft[key] as never;
          setData({ ...latest, preferences: rebased });
          setNotice("偏好已在其他位置更新。已刷新版本并保留本次修改，请检查后重试保存。");
        } catch (refreshReason) {
          setNotice(`${explain(reason)} 当前选择仍保留，可重试保存。${explain(refreshReason)}`);
        }
      } else {
        setNotice(`${explain(reason)} 当前选择仍保留，可重试保存。`);
      }
    }
    finally { setSaving(false); }
  }
  const p = data?.preferences;
  const update = <K extends keyof Preferences["preferences"]>(key: K, value: Preferences["preferences"][K]) => {
    dirtyFields.current.add(key);
    setData((current) => current ? { ...current, preferences: { ...current.preferences, [key]: value } } : current);
  };
  return <section className="data-panel"><div className="panel-heading"><h2>学习与显示偏好</h2></div>{notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}{p ? <form className="support-form" onSubmit={save}><label htmlFor="hint-density">提示密度</label><select id="hint-density" name="hint_density" value={p.hint_density} onChange={(event) => update("hint_density", event.target.value as Preferences["preferences"]["hint_density"])}><option value="standard">标准</option><option value="compact">精简</option><option value="guided">引导更充分</option></select><label htmlFor="response-length">回答长度</label><select id="response-length" name="response_length" value={p.response_length} onChange={(event) => update("response_length", event.target.value as Preferences["preferences"]["response_length"])}><option value="CONCISE">简洁</option><option value="BALANCED">适中</option><option value="DETAILED">详细</option></select><label htmlFor="example-order">讲解顺序</label><select id="example-order" name="example_order" value={p.example_order} onChange={(event) => update("example_order", event.target.value as Preferences["preferences"]["example_order"])}><option value="EXAMPLE_FIRST">先看例子</option><option value="CONCEPT_FIRST">先讲概念</option><option value="ADAPTIVE">根据学习情况调整</option></select><label htmlFor="font-scale">字号</label><select id="font-scale" name="font_scale" value={p.font_scale} onChange={(event) => update("font_scale", event.target.value as Preferences["preferences"]["font_scale"])}><option value="100">标准</option><option value="115">较大</option><option value="130">大字</option></select><label><input type="checkbox" name="reduced_motion" checked={p.reduced_motion} onChange={(event) => update("reduced_motion", event.target.checked)} /> 减少动画</label><label><input type="checkbox" name="notification_in_app" checked={p.notification_in_app} onChange={(event) => update("notification_in_app", event.target.checked)} /> 接收站内提醒</label><p className="empty-state">这些偏好只调整学习呈现方式，不改变课程权限、测评规则或掌握状态。</p><button className="primary-button" disabled={saving}>{saving ? "正在保存…" : "保存偏好"}</button></form> : <p className="empty-state">{notice || "当前无法读取偏好。"}</p>}</section>;
}
