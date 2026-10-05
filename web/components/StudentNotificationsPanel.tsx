"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";

type Notification = { id: string; kind: string; title: string; body: string; read_at: string | null; created_at: string };
const message = (reason: unknown) => reason instanceof ApiError ? reason.message : "通知暂时无法读取。";

export default function StudentNotificationsPanel() {
  const [items, setItems] = useState<Notification[]>([]); const [notice, setNotice] = useState("");
  useEffect(() => { api<Notification[]>("/me/notifications?limit=30").then(setItems).catch((reason) => setNotice(message(reason))); }, []);
  async function markRead(item: Notification) { if (item.read_at) return; try { const next = await api<Notification>(`/me/notifications/${item.id}/read`, { method: "POST" }); setItems((current) => current.map((candidate) => candidate.id === next.id ? next : candidate)); } catch (reason) { setNotice(message(reason)); } }
  return <section className="data-panel"><div className="panel-heading"><h2>站内通知</h2><span aria-live="polite">{items.filter((item) => !item.read_at).length} 条未读</span></div>{notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}{items.length ? items.map((item) => <button type="button" className={item.read_at ? "notification-row read" : "notification-row"} key={item.id} aria-label={`${item.read_at ? "已读" : "标记为已读"}：${item.title}`} onClick={() => void markRead(item)}><span><strong>{item.title}</strong><small>{item.body}</small></span><time dateTime={item.created_at}>{new Date(item.created_at).toLocaleDateString("zh-CN")}</time></button>) : <p className="empty-state">暂无站内通知。</p>}</section>;
}
