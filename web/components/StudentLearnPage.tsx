"use client";

import { FormEvent, Suspense, useEffect, useRef, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { api, ApiError, streamChatTurn } from "../lib/api";
import StudentInterventionRunsPanel from "./StudentInterventionRunsPanel";
import EvidencePointerDrawer from "./learning/EvidencePointerDrawer";

type Material = { id: string; title: string; current_version: null | { id: string; version_no: number; status: string } };
type SearchClosure = { object_id: string; object_type: string; physical_page: number | null; relation_type: string; evidence_pointer_id?: string };
type SearchItem = { text?: string; title?: string; physical_page?: number | null; object_type?: string; evidence_id?: string; evidence_pointer_id?: string; closure?: SearchClosure[] };
type Citation = { pointerId?: string; label: string };
type Turn = { role: "student" | "tutor"; content: string; citations: Citation[]; status?: string };
type SavedChatSession = {
  id: string;
  course_id: string;
  mode: string;
  turns: unknown[];
};
const tutorStageLabels: Record<string, string> = {
  retrieving: "正在检索教材依据…",
  generating: "正在整理回答…",
  verifying: "正在核对回答与引用…",
  safety: "正在检查回答边界…",
};
function reasonText(reason: unknown): string { return reason instanceof ApiError ? reason.message : "请求未完成，请检查本地服务后重试。"; }

function StudentLearnContent() {
  const { courseId } = useParams<{ courseId: string }>();
  const searchParams = useSearchParams();
  const restoreRequested = searchParams.has("session_id");
  const requestedSessionParam = searchParams.get("session_id");
  const requestedSessionId = requestedSessionParam?.trim() ?? "";
  const invalidSessionParam = restoreRequested && !requestedSessionId;
  const [materials, setMaterials] = useState<Material[]>([]); const [query, setQuery] = useState(""); const [tableOnly, setTableOnly] = useState(false); const [results, setResults] = useState<SearchItem[]>([]); const [question, setQuestion] = useState(""); const [turns, setTurns] = useState<Turn[]>([]); const [sessionId, setSessionId] = useState(""); const [loadedSession, setLoadedSession] = useState<{ id: string; courseId: string } | null>(null); const [restoreError, setRestoreError] = useState<{ id: string; courseId: string; message: string } | null>(null); const [notice, setNotice] = useState("正在读取可学习教材…"); const [sending, setSending] = useState(false);
  const sessionMatchesRoute = Boolean(restoreRequested && requestedSessionId && loadedSession?.id === requestedSessionId && loadedSession.courseId === courseId);
  const restoreErrorForRoute = invalidSessionParam
    ? "无法恢复该学习会话。请确认链接有效，或返回课程重新开始。"
    : restoreRequested && restoreError?.id === requestedSessionId && restoreError.courseId === courseId
      ? restoreError.message
      : "";
  const sessionLoading = Boolean(restoreRequested && requestedSessionId && !sessionMatchesRoute && !restoreErrorForRoute);
  const restoreBlocked = sessionLoading || Boolean(restoreErrorForRoute);
  const visibleTurns = sessionId && (loadedSession?.id !== sessionId || loadedSession.courseId !== courseId)
    ? []
    : restoreRequested && !sessionMatchesRoute ? [] : turns;
  const activeSessionForRoute = restoreRequested
    ? (sessionMatchesRoute ? sessionId : "")
    : loadedSession?.id === sessionId && loadedSession.courseId === courseId
      ? sessionId
      : "";
  const sessionRestoreRequested = useRef(false);
  const loadedSessionRef = useRef<{ id: string; courseId: string } | null>(null);
  const pendingTurn = useRef<{ sessionId: string; content: string; clientTurnId: string } | null>(null);
  useEffect(() => { api<Material[]>(`/courses/${courseId}/materials`).then((items) => { setMaterials(items); if (!sessionRestoreRequested.current) setNotice(items.length ? "" : "当前课程还没有已发布的教材。请联系课程内容管理员。"); }).catch((reason) => { if (!sessionRestoreRequested.current) setNotice(reasonText(reason)); }); }, [courseId]);
  useEffect(() => {
    if (!restoreRequested) {
      sessionRestoreRequested.current = false;
      loadedSessionRef.current = null;
      return;
    }

    sessionRestoreRequested.current = true;
    if (requestedSessionId && loadedSessionRef.current?.id === requestedSessionId && loadedSessionRef.current.courseId === courseId) return;
    loadedSessionRef.current = null;
    if (!requestedSessionId) {
      return;
    }

    let active = true;
    api<SavedChatSession>(`/chat/sessions/${encodeURIComponent(requestedSessionId)}`)
      .then((saved) => {
        if (!active) return;
        if (saved.id !== requestedSessionId || saved.course_id !== courseId || saved.mode !== "course_qa") {
          loadedSessionRef.current = null;
          setLoadedSession(null);
          setRestoreError({ id: requestedSessionId, courseId, message: "无法恢复该学习会话。请确认它属于当前课程，或返回课程重新开始。" });
          setTurns([]);
          setSessionId("");
          setNotice("");
          return;
        }

        const restoredTurns: Turn[] = saved.turns.flatMap((value): Turn[] => {
          if (!value || typeof value !== "object") return [];
          const turn = value as { role?: unknown; content?: unknown; citations?: unknown };
          if ((turn.role !== "student" && turn.role !== "tutor") || typeof turn.content !== "string") return [];
          const citations = Array.isArray(turn.citations)
            ? turn.citations.flatMap((item, index): Citation[] => {
                if (!item || typeof item !== "object") return [];
                const citation = item as { evidence_pointer_id?: unknown; label?: unknown };
                const pointerId = typeof citation.evidence_pointer_id === "string" && citation.evidence_pointer_id.trim()
                  ? citation.evidence_pointer_id
                  : undefined;
                return [{
                  pointerId,
                  label: typeof citation.label === "string" && citation.label.trim()
                    ? citation.label
                    : `教材引用 ${index + 1}`,
                }];
              })
            : [];
          return [{ role: turn.role, content: turn.content, citations, status: turn.role === "tutor" ? "已保存回答" : undefined }];
        });
        loadedSessionRef.current = { id: requestedSessionId, courseId };
        setLoadedSession({ id: requestedSessionId, courseId });
        setRestoreError(null);
        setTurns(restoredTurns);
        setSessionId(requestedSessionId);
        setNotice("");
      })
      .catch(() => {
        if (!active) return;
        loadedSessionRef.current = null;
        setLoadedSession(null);
        setRestoreError({ id: requestedSessionId, courseId, message: "无法恢复该学习会话。请确认它属于当前账号和课程，或返回课程重新开始。" });
        setTurns([]);
        setSessionId("");
        setNotice("");
      });
    return () => { active = false; };
  }, [courseId, requestedSessionId, restoreRequested]);
  async function search(event: FormEvent) { event.preventDefault(); if (!query.trim()) return; try { const result = await api<{ items: SearchItem[] }>("/knowledge/search", { method: "POST", body: JSON.stringify({ course_id: courseId, query, top_k: 8, purpose: "course_qa", object_types: tableOnly ? ["table"] : undefined }) }); setResults(result.items); setNotice(result.items.length ? "" : tableOnly ? "没有找到可定位的原生表格，请尝试表格中的完整词项。" : "当前课程教材中没有找到足够依据，请尝试章节名或教材内概念。 "); } catch (reason) { setNotice(reasonText(reason)); } }
  async function send(event: FormEvent) {
    event.preventDefault();
    const content = question.trim();
    if (!content || sending) return;
    setNotice("");
    setSending(true);
    setTurns((items) => [...items, { role: "student", content, citations: [] }, { role: "tutor", content: "", citations: [], status: "正在连接学习助手…" }]);
    try {
      let activeSession = activeSessionForRoute;
      if (!activeSession) {
        const created = await api<{ id: string }>("/chat/sessions", {
          method: "POST",
          body: JSON.stringify({ course_id: courseId, mode: "course_qa", title: "教材学习" }),
        });
        activeSession = created.id;
        loadedSessionRef.current = { id: activeSession, courseId };
        setLoadedSession({ id: activeSession, courseId });
        setRestoreError(null);
        setSessionId(activeSession);
        const currentUrl = new URL(window.location.href);
        currentUrl.searchParams.set("session_id", activeSession);
        window.history.replaceState(window.history.state, "", currentUrl);
      }
      const previous = pendingTurn.current;
      const clientTurnId = previous?.sessionId === activeSession && previous.content === content
        ? previous.clientTurnId
        : crypto.randomUUID();
      pendingTurn.current = { sessionId: activeSession, content, clientTurnId };
      await streamChatTurn(activeSession, content, (eventData) => {
        if (eventData.event === "state") {
          const stage = String(eventData.data.stage ?? "");
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? { ...item, status: tutorStageLabels[stage] ?? "学习助手正在处理当前请求…" }
            : item));
        }
        if (eventData.event === "delta") {
          const text = String(eventData.data.text ?? "");
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? { ...item, content: item.content + text }
            : item));
        }
        if (eventData.event === "citation") {
          const citation = {
            label: String(eventData.data.label ?? "教材证据"),
            pointerId: typeof eventData.data.evidence_pointer_id === "string"
              ? eventData.data.evidence_pointer_id
              : undefined,
          };
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? { ...item, citations: [...item.citations, citation] }
            : item));
        }
        if (eventData.event === "done") {
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? { ...item, status: eventData.data.saved === true ? "回答已保存" : "回答尚未确认保存" }
            : item));
        }
        if (eventData.event === "error") {
          setNotice(String(eventData.data.message ?? "暂时无法完成回答。"));
        }
      }, clientTurnId);
      pendingTurn.current = null;
      setQuestion("");
    } catch (reason) {
      setTurns((items) => items.slice(0, -2));
      setQuestion(content);
      setNotice(`${reasonText(reason)} 你的问题仍保留在输入框；网络恢复后重新发送会继续使用同一回合编号。`);
    } finally {
      setSending(false);
    }
  }
  const visibleNotice = restoreErrorForRoute || (sessionLoading ? "正在恢复已保存的学习会话…" : notice);
  return <div className="student-learn-page"><div className="page-heading"><div><h1>学习</h1><p>从已发布教材中检索内容，并基于教材证据提问。</p></div></div>{visibleNotice && <p className="status-banner" role="status" aria-live="polite"><Icon icon="solar:info-circle-linear" />{visibleNotice}</p>}<StudentInterventionRunsPanel courseId={courseId} /><div className="learn-layout"><aside className="learn-materials"><h2>课程教材</h2>{materials.length ? materials.map((material) => <div className="learn-material-row" key={material.id}><Icon icon="solar:book-bookmark-linear" /><span><strong>{material.title}</strong><small>版本 {material.current_version?.version_no ?? "—"}</small></span></div>) : <p className="empty-state">暂时没有可学习教材。</p>}</aside><section className="learn-evidence"><form className="learn-search" onSubmit={search}><label htmlFor="course-search">搜索教材</label><div><input id="course-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入概念、章节或问题" disabled={!materials.length} /><button className="primary-button" disabled={!materials.length}>搜索</button></div><label><input checked={tableOnly} onChange={(event) => setTableOnly(event.target.checked)} type="checkbox" />只看表格</label></form>{results.length ? <section className="evidence-list"><h2>教材依据</h2>{results.map((item, index) => <article key={item.evidence_id ?? index}><strong>{item.object_type === "table" ? "表格对象 · " : "教材内容 · "}{item.title ?? "教材内容"}{item.physical_page ? ` · 第 ${item.physical_page} 页` : ""}</strong><p>{item.text ?? "未返回可显示的教材片段。"}</p><small>{item.evidence_id ? "已找到教材依据" : "教材结果"}</small>{item.evidence_pointer_id && <EvidencePointerDrawer label={item.object_type === "table" ? "查看表格固定来源" : "查看固定来源快照"} pointerId={item.evidence_pointer_id} />}{item.closure?.filter((neighbor) => neighbor.object_type === "figure" && neighbor.evidence_pointer_id).map((neighbor) => <div key={neighbor.object_id}><small>阅读顺序相邻图像 · 仅定位{neighbor.physical_page ? ` · 物理页 ${neighbor.physical_page}` : ""}</small><EvidencePointerDrawer label="定位相邻图像" pointerId={neighbor.evidence_pointer_id!} /></div>)}</article>)}</section> : <section className="learn-empty"><Icon icon="solar:book-2-linear" /><h2>从教材开始学习</h2><p>输入课程内的概念或问题，系统会先查找教材依据。</p></section>}</section><section className="learn-tutor"><header><div><h2>学习助手</h2><p>回答以当前课程教材为依据。</p></div><Icon icon="solar:chat-round-dots-linear" /></header><div className="learn-turns" aria-live="polite" aria-relevant="additions text">{visibleTurns.length ? visibleTurns.map((turn, index) => <article className={`learn-turn ${turn.role}`} key={index}><strong>{turn.role === "student" ? "我" : "学习助手"}</strong><p>{turn.content || "正在整理教材依据…"}</p>{turn.status && <small className="learn-turn-status" role="status">{turn.status}</small>}{turn.citations.map((citation, citationIndex) => <div className="learn-citation" key={`${citation.pointerId ?? citation.label}-${citationIndex}`}><small><Icon icon="solar:book-bookmark-linear" />{citation.label}</small>{citation.pointerId && <EvidencePointerDrawer label="打开引用" pointerId={citation.pointerId} />}</div>)}</article>) : <p className="empty-state">你可以围绕当前教材提问；证据不足时会明确说明。</p>}</div><form className="learn-composer" onSubmit={send}><input aria-label="围绕教材提问" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="围绕教材提问…" disabled={!materials.length || sending || restoreBlocked} /><button type="submit" disabled={!materials.length || sending || restoreBlocked} aria-label="发送问题"><Icon icon="solar:plain-2-bold" /></button></form></section></div></div>;
}

export default function StudentLearnPage() {
  return (
    <Suspense fallback={<p className="status-banner" role="status">正在读取学习空间…</p>}>
      <StudentLearnContent />
    </Suspense>
  );
}
