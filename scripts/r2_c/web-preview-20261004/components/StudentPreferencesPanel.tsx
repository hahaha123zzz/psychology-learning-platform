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
  useEffect(() => { api<Preferences>("/me/preferences").then((next) => { setData(next); setNotice(""); }).catch((reason) => setNotice(explain(reason))); }, []);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!data) return;
    const form = new FormData(event.currentTarget);
    try {
      const next = await api<Preferences>("/me/preferences", { method: "PATCH", body: JSON.stringify({ version: data.version, hint_density: form.get("hint_density"), font_scale: form.get("font_scale"), reduced_motion: form.get("reduced_motion") === "on", notification_in_app: form.get("notification_in_app") === "on" }) });
      setData(next); setNotice("偏好已保存；偏好不会解除考试或权限限制。 ");
    } catch (reason) { setNotice(explain(reason)); }
  }
  const p = data?.preferences;
  return <section className="data-panel"><div className="panel-heading"><h2>学习与显示偏好</h2></div>{notice && <p className="status-banner">{notice}</p>}{p && <form className="support-form" onSubmit={save}><label>提示密度<select name="hint_density" defaultValue={p.hint_density}><option value="standard">标准</option><option value="compact">精简</option><option value="guided">引导更充分</option></select></label><label>字号<select name="font_scale" defaultValue={p.font_scale}><option value="100">标准</option><option value="115">较大</option><option value="130">大字</option></select></label><label><input type="checkbox" name="reduced_motion" defaultChecked={p.reduced_motion} /> 减少动画</label><label><input type="checkbox" name="notification_in_app" defaultChecked={p.notification_in_app} /> 接收站内提醒</label><button className="primary-button">保存偏好</button></form>}</section>;
}
