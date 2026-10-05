"use client";

import { FormEvent, useEffect, useState } from "react";
import { ApiError, api } from "../lib/api";

type Preferences = {
  user_id: string;
  preferences: {
    hint_density: "standard" | "compact" | "guided";
    reduced_motion: boolean;
    font_scale: "100" | "115" | "130";
    notification_in_app: boolean;
  };
  version: number;
};

const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "偏好保存失败。";

export default function StudentPreferencesPanel() {
  const [data, setData] = useState<Preferences | null>(null);
  const [notice, setNotice] = useState("正在读取偏好…");
  const [saving, setSaving] = useState(false);
  useEffect(() => { api<Preferences>("/me/preferences").then((next) => { setData(next); setNotice(""); }).catch((reason) => setNotice(explain(reason))); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data || saving) return;
    setSaving(true);
    setNotice("");
    try {
      const next = await api<Preferences>("/me/preferences", { method: "PATCH", body: JSON.stringify({ version: data.version, ...data.preferences }) });
      setData(next); setNotice("偏好已保存。网络中断时，本页会保留尚未确认的选择，可再次保存。");
    } catch (reason) { setNotice(`${explain(reason)} 当前选择仍保留，可重试保存。`); }
    finally { setSaving(false); }
  }
  const p = data?.preferences;
  const update = (key: keyof Preferences["preferences"], value: string | boolean) => {
    setData((current) => current ? { ...current, preferences: { ...current.preferences, [key]: value } } : current);
  };
  return <section className="data-panel"><div className="panel-heading"><h2>学习与显示偏好</h2></div>{notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}{p ? <form className="support-form" onSubmit={save}><label htmlFor="hint-density">提示密度</label><select id="hint-density" name="hint_density" value={p.hint_density} onChange={(event) => update("hint_density", event.target.value as Preferences["preferences"]["hint_density"])}><option value="standard">标准</option><option value="compact">精简</option><option value="guided">引导更充分</option></select><label htmlFor="font-scale">字号</label><select id="font-scale" name="font_scale" value={p.font_scale} onChange={(event) => update("font_scale", event.target.value as Preferences["preferences"]["font_scale"])}><option value="100">标准</option><option value="115">较大</option><option value="130">大字</option></select><label><input type="checkbox" name="reduced_motion" checked={p.reduced_motion} onChange={(event) => update("reduced_motion", event.target.checked)} /> 减少动画</label><label><input type="checkbox" name="notification_in_app" checked={p.notification_in_app} onChange={(event) => update("notification_in_app", event.target.checked)} /> 接收站内提醒</label><p className="empty-state">这些偏好只调整学习呈现方式，不改变课程权限、测评规则或掌握状态。</p><button className="primary-button" disabled={saving}>{saving ? "正在保存…" : "保存偏好"}</button></form> : <p className="empty-state">{notice || "当前无法读取偏好。"}</p>}</section>;
}
