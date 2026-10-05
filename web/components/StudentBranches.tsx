"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError, idempotencyKey, streamChatTurn } from "../lib/api";

type Session = {
  id: string;
  course_id: string;
  title?: string;
  mode: string;
  updated_at: string;
};
type Turn = { id: string; role: string; content: string };
type BranchCreated = { id: string; parent_session_id: string; selection: string };

const fail = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "请求失败，请保留当前内容后重试。";

export default function StudentBranches() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [parent, setParent] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [sourceTurnId, setSourceTurnId] = useState("");
  const [branch, setBranch] = useState<BranchCreated | null>(null);
  const [selection, setSelection] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [mergeNote, setMergeNote] = useState("");
  const [mergeConfirmed, setMergeConfirmed] = useState(false);
  const [mergeKey, setMergeKey] = useState("");
  const [notice, setNotice] = useState("正在读取你的主会话…");
  const [busy, setBusy] = useState(false);

  const studentTurns = useMemo(
    () => turns.filter((turn) => turn.role === "student"),
    [turns],
  );

  useEffect(() => {
    let active = true;
    api<Session[]>("/chat/sessions")
      .then((items) => {
        if (!active) return;
        setSessions(items);
        setParent(items[0]?.id ?? "");
        setNotice(items.length ? "" : "还没有可用的主会话，请先进入学习空间发起对话。" );
      })
      .catch((reason) => active && setNotice(fail(reason)));
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!parent) return;
    let active = true;
    api<{ turns: Turn[] }>(`/chat/sessions/${parent}`)
      .then((data) => {
        if (!active) return;
        const student = data.turns.filter((turn) => turn.role === "student");
        setTurns(data.turns);
        setSourceTurnId(student.at(-1)?.id ?? "");
        setNotice(student.length ? "" : "该会话还没有学生发言，暂时不能从中创建局部分支。" );
      })
      .catch((reason) => active && setNotice(fail(reason)));
    return () => {
      active = false;
    };
  }, [parent]);

  async function create(event: FormEvent) {
    event.preventDefault();
    const source = studentTurns.find((turn) => turn.id === sourceTurnId);
    const normalizedSelection = selection.trim();
    if (!parent || !source || !normalizedSelection || !source.content.includes(normalizedSelection)) {
      setNotice("请选择一条本人发言，并填写其中连续出现的原文片段。来源不匹配时服务端会拒绝创建。");
      return;
    }
    setBusy(true);
    try {
      const created = await api<BranchCreated>(`/chat/sessions/${parent}/branches`, {
        method: "POST",
        body: JSON.stringify({
          source_turn_id: source.id,
          selection: normalizedSelection,
          title: "局部追问",
        }),
      });
      setBranch(created);
      setSelection(normalizedSelection);
      setAnswer("");
      setQuestion("");
      setMergeNote("");
      setMergeConfirmed(false);
      setMergeKey("");
      setNotice("局部分支已创建；分支回答不会自动写回主会话或学习记忆。");
    } catch (reason) {
      setNotice(fail(reason));
    } finally {
      setBusy(false);
    }
  }

  async function ask(event: FormEvent) {
    event.preventDefault();
    if (!branch || !question.trim() || busy) return;
    setBusy(true);
    setAnswer("");
    setNotice("");
    try {
      await streamChatTurn(branch.id, question.trim(), (eventData) => {
        if (eventData.event === "delta") {
          setAnswer((value) => value + String(eventData.data.text ?? ""));
        }
        if (eventData.event === "error") {
          setNotice(String(eventData.data.message ?? "分支问答失败；可保留问题后重试。"));
        }
      });
      setQuestion("");
    } catch (reason) {
      setNotice(fail(reason));
    } finally {
      setBusy(false);
    }
  }

  async function merge() {
    if (!branch || busy) return;
    if (!mergeConfirmed) {
      setNotice("请先勾选确认，说明这是你明确选择带回主会话的内容。");
      return;
    }
    if (!mergeNote.trim()) {
      setNotice("请填写要带回主会话的个人说明；系统不会自动合并 AI 的结论。");
      return;
    }
    const requestKey = mergeKey || idempotencyKey();
    setMergeKey(requestKey);
    setBusy(true);
    try {
      await api(`/chat/sessions/${parent}/branches/${branch.id}/merge`, {
        method: "POST",
        body: JSON.stringify({
          note: mergeNote.trim(),
          merge_key: requestKey,
          confirmed: true,
        }),
      });
      setBranch(null);
      setMergeNote("");
      setMergeConfirmed(false);
      setMergeKey("");
      setNotice("已按你的明确确认，将你提供的选段和说明作为学生内容带回主会话。");
    } catch (reason) {
      // 重试沿用同一 key；异 payload 冲突时需先核对服务端状态，不能悄悄换 key 覆盖。
      setNotice(fail(reason));
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="functional-app">
      <header className="app-header">
        <Link href="/" className="app-brand">
          <Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台
        </Link>
        <Link href="/student">主学习空间</Link>
        <strong>局部追问</strong>
      </header>
      <section className="functional-main">
        <div className="section-title">
          <div>
            <p className="eyebrow">独立分支 · 明确确认后才合并</p>
            <h1>局部追问</h1>
            <p>分支不会自动写回主会话、学习状态或记忆；合并只提交你选择的原文和个人说明。</p>
          </div>
        </div>
        {notice && <p className="status-banner" role="status">{notice}</p>}
        <section className="data-grid">
          <section className="data-panel">
            <h2>选择主会话和本人发言</h2>
            <label className="field-label" htmlFor="branch-parent">主会话</label>
            <select
              id="branch-parent"
              className="full-select"
              value={parent}
              onChange={(event) => {
                setParent(event.target.value);
                setTurns([]);
                setSourceTurnId("");
                setBranch(null);
                setSelection("");
                setMergeNote("");
                setMergeConfirmed(false);
                setMergeKey("");
                setNotice("正在读取主会话内容…");
              }}
              disabled={!sessions.length || busy}
            >
              {sessions.map((session) => (
                <option key={session.id} value={session.id}>
                  {session.title ?? session.mode} · {new Date(session.updated_at).toLocaleString("zh-CN")}
                </option>
              ))}
            </select>
            <label className="field-label" htmlFor="branch-source">来源发言</label>
            <select
              id="branch-source"
              className="full-select"
              value={sourceTurnId}
              onChange={(event) => setSourceTurnId(event.target.value)}
              disabled={!studentTurns.length || busy}
            >
              {studentTurns.map((turn, index) => (
                <option key={turn.id} value={turn.id}>
                  第 {index + 1} 条：{turn.content.slice(0, 90)}
                </option>
              ))}
            </select>
            <form className="stack-form" onSubmit={create}>
              <label className="field-label" htmlFor="branch-selection">从该发言中复制连续原文片段</label>
              <textarea
                id="branch-selection"
                value={selection}
                onChange={(event) => setSelection(event.target.value)}
                maxLength={2000}
                placeholder="局部分支只接受本人原始发言中的文本，不接受 AI 回复片段。"
                required
              />
              <button className="primary-button" disabled={!parent || busy || !studentTurns.length}>
                {busy ? "处理中…" : "创建局部分支"}
              </button>
            </form>
          </section>
          <section className="data-panel">
            <h2>分支追问与确认合并</h2>
            {branch ? (
              <>
                <p className="eyebrow">选中的原文</p>
                <blockquote>{branch.selection}</blockquote>
                <form className="composer" onSubmit={ask}>
                  <label className="sr-only" htmlFor="branch-question">围绕选段继续追问</label>
                  <input
                    id="branch-question"
                    value={question}
                    onChange={(event) => setQuestion(event.target.value)}
                    placeholder="围绕选段继续追问…"
                    maxLength={4000}
                    disabled={busy}
                  />
                  <button aria-label="发送追问" disabled={busy || !question.trim()}>
                    <Icon icon="solar:plain-2-bold" />
                  </button>
                </form>
                {answer && <article className="live-turn tutor"><strong>AI 教师 · 分支回答</strong><p>{answer}</p></article>}
                <label className="field-label" htmlFor="branch-merge-note">你希望带回主会话的说明</label>
                <textarea
                  id="branch-merge-note"
                  value={mergeNote}
                  onChange={(event) => setMergeNote(event.target.value)}
                  maxLength={5000}
                  placeholder="只写你自己的总结、问题或补充；AI 分支结论不会被当作你的原话合并。"
                  disabled={busy || Boolean(mergeKey)}
                />
                <label className="checkbox-row">
                  <input
                    type="checkbox"
                    checked={mergeConfirmed}
                    onChange={(event) => setMergeConfirmed(event.target.checked)}
                    disabled={busy}
                  />
                  我确认将上方原文片段和自己的说明带回主会话。
                </label>
                <button
                  className="secondary-button"
                  onClick={() => void merge()}
                  disabled={busy || !mergeConfirmed || !mergeNote.trim()}
                >
                  {busy ? "处理中…" : "确认并带回主会话"}
                </button>
              </>
            ) : (
              <p className="empty-state">选择一条本人发言并创建分支后，可在这里独立追问。</p>
            )}
          </section>
        </section>
      </section>
    </main>
  );
}
