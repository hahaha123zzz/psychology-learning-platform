"use client";

import { FormEvent, useEffect, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError, streamChatTurn } from "../lib/api";

type Session = { id: string; title?: string; mode: string; updated_at: string };
type Turn = { id: string; role: string; content: string };
const fail = (reason: unknown) => reason instanceof ApiError ? reason.message : "请求失败。";

export default function StudentBranches() {
  const [sessions, setSessions] = useState<Session[]>([]); const [parent, setParent] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]); const [branch, setBranch] = useState("");
  const [selection, setSelection] = useState(""); const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => { api<Session[]>("/chat/sessions").then(items => { setSessions(items); setParent(items[0]?.id ?? ""); }).catch(reason => setNotice(fail(reason))); }, []);
  useEffect(() => { if (!parent) return; api<{ turns: Turn[] }>(`/chat/sessions/${parent}`).then(data => setTurns(data.turns)).catch(reason => setNotice(fail(reason))); }, [parent]);
  async function create(event: FormEvent) {
    event.preventDefault(); const source = turns.filter(turn => turn.role === "tutor").at(-1);
    if (!source || !selection.trim()) return setNotice("请选择有 AI 回答的主会话，并填写局部选段。");
    try { const data = await api<{ id: string }>(`/chat/sessions/${parent}/branches`, { method: "POST", body: JSON.stringify({ source_turn_id: source.id, selection, title: "局部追问" }) }); setBranch(data.id); setNotice("局部分支已创建，可在下方独立追问。"); } catch (reason) { setNotice(fail(reason)); }
  }
  async function ask(event: FormEvent) {
    event.preventDefault(); if (!branch || !question.trim()) return; setAnswer("");
    try { await streamChatTurn(branch, question, eventData => { if (eventData.event === "delta") setAnswer(value => value + String(eventData.data.text ?? "")); if (eventData.event === "error") setNotice(String(eventData.data.message ?? "分支问答失败")); }); setQuestion(""); } catch (reason) { setNotice(fail(reason)); }
  }
  async function merge() {
    if (!branch) return; const note = prompt("确认带回主会话的笔记："); if (!note) return;
    try { await api(`/chat/sessions/${parent}/branches/${branch}/merge`, { method: "POST", body: JSON.stringify({ note }) }); setNotice("分支内容已按你的确认合并回主会话。"); setBranch(""); } catch (reason) { setNotice(fail(reason)); }
  }
  return <main className="functional-app"><header className="app-header"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><Link href="/student">主对话</Link><strong>局部追问</strong></header><section className="functional-main"><div className="section-title"><div><p className="eyebrow">独立分支，确认后才合并</p><h1>局部追问</h1><p>分支不会自动写回主会话或学习记忆。</p></div></div>{notice && <p className="status-banner">{notice}</p>}<section className="data-grid"><section className="data-panel"><h2>选择主会话</h2><select className="full-select" value={parent} onChange={event => setParent(event.target.value)}>{sessions.map(session => <option key={session.id} value={session.id}>{session.title ?? session.mode} · {new Date(session.updated_at).toLocaleString("zh-CN")}</option>)}</select><form className="stack-form" onSubmit={create}><textarea value={selection} onChange={event => setSelection(event.target.value)} placeholder="从 AI 回答中复制需要继续追问的局部文本" /><button className="primary-button">创建局部分支</button></form></section><section className="data-panel"><h2>分支对话</h2>{branch ? <><p className="empty-state">分支 ID：{branch}</p><form className="composer" onSubmit={ask}><input value={question} onChange={event => setQuestion(event.target.value)} placeholder="围绕选段继续追问…" /><button><Icon icon="solar:plain-2-bold" /></button></form>{answer && <article className="live-turn tutor"><strong>AI 教师</strong><p>{answer}</p></article>}<button className="secondary-button" onClick={() => void merge()}>确认并带回主对话</button></> : <p className="empty-state">先从左侧创建分支。</p>}</section></section></section></main>;
}
