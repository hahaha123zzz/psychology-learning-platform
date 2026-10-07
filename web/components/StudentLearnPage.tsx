"use client";

import { FormEvent, Suspense, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Icon } from "@iconify/react";
import { api, ApiError, streamChatTurn } from "../lib/api";
import { clearReaderSelection, clearReaderSelectionForCourse, persistReaderSelection, readReaderSelectionPointerId, subscribeReaderSelectionContext } from "../lib/reader-selection-context";
import StudentInterventionRunsPanel from "./StudentInterventionRunsPanel";
import EvidencePointerDrawer from "./learning/EvidencePointerDrawer";
import StudentProvenanceMetadata from "./learning/StudentProvenanceMetadata";
import { studentMaterialVersion } from "../lib/student-material-version";
import { materialTypeLabel } from "../lib/material-type-label";
import { readStudentProvenance, type StudentProvenance } from "../lib/student-provenance";

type Material = { id: string; title: string; current_version: null | { id: string; version_no: number; status: string }; learning_version?: null | { id: string; version_no: number; status: string } };
type SearchClosure = { object_id: string; object_type: string; physical_page: number | null; relation_type: string; evidence_pointer_id?: string | null };
type SearchItem = { text?: string; title?: string; physical_page?: number | null; object_type?: string; material_type?: string | null; evidence_id?: string; evidence_pointer_id?: string; closure?: SearchClosure[] };
type Citation = { pointerId?: string; label: string; materialType?: string | null; provenance: StudentProvenance | null };
type Turn = { role: "student" | "tutor"; content: string; citations: Citation[]; status?: string; explanation?: "table"; pendingExplanation?: "table" };
type TablePointerResponse = {
  evidence_pointer_id: string;
  course_id: string | null;
  material_title: string;
  chapter_path: string | null;
  physical_page: number | null;
  object_type: string;
  excerpt: string;
  material_id: string;
  material_version_id: string;
  publication_snapshot_id: string | null;
  index_job_id: string | null;
  domain_release_id: string | null;
};
type SelectedTablePointer = Omit<TablePointerResponse, "course_id" | "excerpt">;
type SavedChatSession = {
  id: string;
  course_id: string;
  mode: string;
  turns: unknown[];
};
const tutorStageLabels: Record<string, string> = {
  retrieving: "正在检索课程资料…",
  generating: "正在整理回答…",
  verifying: "正在核对回答与引用…",
  safety: "正在检查回答边界…",
};
function reasonText(reason: unknown): string { return reason instanceof ApiError ? reason.message : "请求未完成，请检查本地服务后重试。"; }

// EVID-011 仅在服务端确认完整 Release pin 后才会给 closure 附加 Reader pointer ID。
function isPinnedParagraphContext(
  neighbor: SearchClosure,
): neighbor is SearchClosure & { evidence_pointer_id: string } {
  return (
    neighbor.object_type === "paragraph" &&
    (neighbor.relation_type === "caption_of" || neighbor.relation_type === "explains") &&
    typeof neighbor.evidence_pointer_id === "string" &&
    neighbor.evidence_pointer_id.trim().length > 0
  );
}

function StudentLearnContent({ courseId }: { courseId: string }) {
  const searchParams = useSearchParams();
  const restoreRequested = searchParams.has("session_id");
  const requestedSessionParam = searchParams.get("session_id");
  const requestedSessionId = requestedSessionParam?.trim() ?? "";
  const invalidSessionParam = restoreRequested && !requestedSessionId;
  const [materials, setMaterials] = useState<Material[]>([]); const [query, setQuery] = useState(""); const [tableOnly, setTableOnly] = useState(false); const [results, setResults] = useState<SearchItem[]>([]); const [question, setQuestion] = useState(""); const [turns, setTurns] = useState<Turn[]>([]); const [sessionId, setSessionId] = useState(""); const [loadedSession, setLoadedSession] = useState<{ id: string; courseId: string } | null>(null); const [restoreError, setRestoreError] = useState<{ id: string; courseId: string; message: string } | null>(null); const [notice, setNotice] = useState("正在读取可学习资料…"); const [sending, setSending] = useState(false); const [selectedTablePointer, setSelectedTablePointer] = useState<SelectedTablePointer | null>(null); const [loadingTablePointer, setLoadingTablePointer] = useState(false);
  const selectionContextPointerId = useSyncExternalStore(
    subscribeReaderSelectionContext,
    () => readReaderSelectionPointerId(courseId),
    () => "",
  );
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
  const pendingTurn = useRef<{ sessionId: string; content: string; selectedPointerId?: string; clientTurnId: string } | null>(null);
  useEffect(() => { clearReaderSelectionForCourse(courseId); }, [courseId]);
  function returnReaderSelection(pointerId: string) {
    if (pointerId.trim()) persistReaderSelection(courseId, pointerId);
  }
  useEffect(() => { api<Material[]>(`/courses/${courseId}/materials`).then((items) => { setMaterials(items); if (!sessionRestoreRequested.current) setNotice(items.length ? "" : "当前课程还没有已发布资料。请联系课程内容管理员。"); }).catch((reason) => { if (!sessionRestoreRequested.current) setNotice(reasonText(reason)); }); }, [courseId]);
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
          const turn = value as { role?: unknown; content?: unknown; citations?: unknown; verification?: unknown };
          if ((turn.role !== "student" && turn.role !== "tutor") || typeof turn.content !== "string") return [];
          const citations = Array.isArray(turn.citations)
            ? turn.citations.flatMap((item, index): Citation[] => {
                if (!item || typeof item !== "object") return [];
                const citation = item as { evidence_pointer_id?: unknown; label?: unknown; material_type?: unknown; provenance?: unknown };
                const pointerId = typeof citation.evidence_pointer_id === "string" && citation.evidence_pointer_id.trim()
                  ? citation.evidence_pointer_id
                  : undefined;
                return [{
                  pointerId,
                  label: typeof citation.label === "string" && citation.label.trim()
                    ? citation.label
                    : `资料引用 ${index + 1}`,
                  materialType: typeof citation.material_type === "string" ? citation.material_type : null,
                  provenance: readStudentProvenance(citation.provenance),
                }];
              })
            : [];
          const verification = turn.verification && typeof turn.verification === "object"
            ? turn.verification as { object_context?: unknown }
            : null;
          const objectContext = verification?.object_context && typeof verification.object_context === "object"
            ? verification.object_context as { type?: unknown; evidence_pointer_id?: unknown }
            : null;
          const isVerifiedTableTurn = turn.role === "tutor" && objectContext?.type === "table" &&
            typeof objectContext.evidence_pointer_id === "string" &&
            citations.some((citation) => citation.pointerId === objectContext.evidence_pointer_id);
          return [{
            role: turn.role,
            content: turn.content,
            citations,
            status: turn.role === "tutor" ? "已保存回答" : undefined,
            explanation: isVerifiedTableTurn ? "table" : undefined,
          }];
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
  async function selectTablePointer(pointerId: string) {
    if (sending || loadingTablePointer) return;
    setLoadingTablePointer(true);
    setNotice("");
    try {
      const pointer = await api<TablePointerResponse>(`/evidence-pointers/${encodeURIComponent(pointerId)}`);
      if (
        pointer.evidence_pointer_id !== pointerId ||
        pointer.course_id !== courseId ||
        pointer.object_type !== "table" ||
        !pointer.excerpt.trim()
      ) {
        throw new Error("该引用不是可解释的已验证表格。");
      }
      setSelectedTablePointer({
        evidence_pointer_id: pointer.evidence_pointer_id,
        material_title: pointer.material_title,
        material_id: pointer.material_id,
        material_version_id: pointer.material_version_id,
        publication_snapshot_id: pointer.publication_snapshot_id,
        index_job_id: pointer.index_job_id,
        domain_release_id: pointer.domain_release_id,
        chapter_path: pointer.chapter_path,
        physical_page: pointer.physical_page,
        object_type: pointer.object_type,
      });
      setQuestion((current) => current.trim() ? current : "请解释这张表格的主要信息。");
    } catch (reason) {
      setSelectedTablePointer(null);
      setNotice(reason instanceof ApiError ? reason.message : "无法确认这条表格引用，请从检索结果重新打开。 ");
    } finally {
      setLoadingTablePointer(false);
    }
  }
  async function search(event: FormEvent) { event.preventDefault(); if (!query.trim()) return; try { const result = await api<{ items: SearchItem[] }>("/knowledge/search", { method: "POST", body: JSON.stringify({ course_id: courseId, query, top_k: 8, purpose: "course_qa", object_types: tableOnly ? ["table"] : undefined }) }); setResults(result.items); setNotice(result.items.length ? "" : tableOnly ? "没有找到可定位的原生表格，请尝试表格中的完整词项。" : "当前课程资料中没有找到足够依据，请尝试章节名或概念。 "); } catch (reason) { setNotice(reasonText(reason)); } }
  async function send(event: FormEvent) {
    event.preventDefault();
    const content = question.trim();
    if (!content || sending) return;
    const selectedPointerId = selectedTablePointer?.evidence_pointer_id;
    setNotice("");
    setSending(true);
    setTurns((items) => [...items, { role: "student", content, citations: [] }, { role: "tutor", content: "", citations: [], status: "正在连接学习助手…" }]);
    try {
      let activeSession = activeSessionForRoute;
      if (!activeSession) {
        const created = await api<{ id: string }>("/chat/sessions", {
          method: "POST",
          body: JSON.stringify({ course_id: courseId, mode: "course_qa", title: "课程资料学习" }),
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
      const clientTurnId = previous?.sessionId === activeSession && previous.content === content && previous.selectedPointerId === selectedPointerId
        ? previous.clientTurnId
        : crypto.randomUUID();
      pendingTurn.current = { sessionId: activeSession, content, selectedPointerId, clientTurnId };
      await streamChatTurn(activeSession, content, (eventData) => {
        if (eventData.event === "state") {
          const stage = String(eventData.data.stage ?? "");
          const isVerifiedTableExplanation = stage === "explaining_object" &&
            eventData.data.object_type === "table" &&
            typeof eventData.data.evidence_pointer_id === "string" &&
            eventData.data.evidence_pointer_id === selectedPointerId;
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? {
                ...item,
                ...(isVerifiedTableExplanation ? { pendingExplanation: "table" as const } : {}),
                status: isVerifiedTableExplanation
                  ? "正在整理这张已核验表格的解释…"
                  : tutorStageLabels[stage] ?? "学习助手正在处理当前请求…",
              }
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
            label: String(eventData.data.label ?? "课程资料来源"),
            materialType: typeof eventData.data.material_type === "string" ? eventData.data.material_type : null,
            provenance: readStudentProvenance(eventData.data.provenance),
            pointerId: typeof eventData.data.evidence_pointer_id === "string"
              ? eventData.data.evidence_pointer_id
              : undefined,
          };
          setTurns((items) => items.map((item, index) => index === items.length - 1
            ? { ...item, citations: [...item.citations, citation] }
            : item));
        }
        if (eventData.event === "done") {
          setTurns((items) => items.map((item, index) => {
            if (index !== items.length - 1) return item;
            const hasExactTableCitation = item.citations.some((citation) => citation.pointerId === selectedPointerId);
            const savedTableExplanation = eventData.data.saved === true && item.pendingExplanation === "table" && hasExactTableCitation;
            return {
              ...item,
              explanation: savedTableExplanation ? "table" : undefined,
              pendingExplanation: undefined,
              status: eventData.data.saved === true
                ? item.pendingExplanation === "table" && !hasExactTableCitation
                  ? "回答已保存，但没有收到这张表格的精确引用。"
                  : "回答已保存"
                : "回答尚未确认保存",
            };
          }));
        }
        if (eventData.event === "error") {
          setNotice(String(eventData.data.message ?? "暂时无法完成回答。"));
        }
      }, clientTurnId, selectedPointerId ? [selectedPointerId] : undefined);
      pendingTurn.current = null;
      setQuestion("");
      setSelectedTablePointer(null);
    } catch (reason) {
      setTurns((items) => items.slice(0, -2));
      setQuestion(content);
      setNotice(`${reasonText(reason)} 你的问题仍保留在输入框；网络恢复后重新发送会继续使用同一回合编号。`);
    } finally {
      setSending(false);
    }
  }
  const visibleNotice = restoreErrorForRoute || (sessionLoading ? "正在恢复已保存的学习会话…" : notice);
  return <div className="student-learn-page"><div className="page-heading"><div><h1>学习</h1><p>从当前课程资料中检索内容，并查看可核验的来源。</p></div><Link className="secondary-button" href="/student/learning">返回引导学习任务</Link></div>{visibleNotice && <p className="status-banner" role="status" aria-live="polite"><Icon icon="solar:info-circle-linear" />{visibleNotice}</p>}<StudentInterventionRunsPanel courseId={courseId} /><div className="learn-layout"><aside className="learn-materials"><h2>课程资料</h2>{materials.length ? materials.map((material) => { const version = studentMaterialVersion(material); return <div className="learn-material-row" key={material.id}><Icon icon="solar:book-bookmark-linear" /><span><strong>{material.title}</strong><small>版本 {version?.version_no ?? "—"}</small></span></div>; }) : <p className="empty-state">暂时没有可学习资料。</p>}</aside><section className="learn-evidence"><form className="learn-search" onSubmit={search}><label htmlFor="course-search">搜索课程资料</label><div><input id="course-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="输入概念、章节或问题" disabled={!materials.length} /><button className="primary-button" disabled={!materials.length}>搜索</button></div><label><input checked={tableOnly} onChange={(event) => setTableOnly(event.target.checked)} type="checkbox" />只看表格</label></form>{results.length ? <section className="evidence-list"><h2>检索来源</h2>{results.map((item, index) => <article key={item.evidence_id ?? index}><strong>{materialTypeLabel(item.material_type)} · {item.object_type === "table" ? "表格对象 · " : item.object_type === "figure" ? "图像对象 · " : "资料段落 · "}{item.title ?? "资料片段"}{item.physical_page ? ` · 第 ${item.physical_page} 页` : ""}</strong><p>{item.text ?? "未返回可显示的资料片段。"}</p><small>{item.evidence_id ? "已找到检索来源" : "检索结果"}</small>{item.evidence_pointer_id && <EvidencePointerDrawer label={item.object_type === "table" ? "查看表格固定来源" : "查看固定来源快照"} onAskTutor={item.object_type === "table" ? selectTablePointer : undefined} onReturnToLearn={returnReaderSelection} pointerId={item.evidence_pointer_id} />}{item.closure?.filter(isPinnedParagraphContext).map((neighbor) => <div key={`${neighbor.object_id}-${neighbor.relation_type}`} className="learn-closure-context"><small>{neighbor.relation_type === "caption_of" ? "图注上下文（非独立检索命中）" : "解释段落上下文（非独立检索命中）"}{neighbor.physical_page ? ` · 第 ${neighbor.physical_page} 页` : ""}</small><EvidencePointerDrawer label={neighbor.relation_type === "caption_of" ? "查看图注来源" : "查看相邻段落来源"} onReturnToLearn={returnReaderSelection} pointerId={neighbor.evidence_pointer_id} /></div>)}{item.closure?.filter((neighbor) => neighbor.object_type === "figure" && (neighbor.relation_type === "previous" || neighbor.relation_type === "next") && neighbor.evidence_pointer_id).map((neighbor) => <div key={neighbor.object_id}><small>阅读顺序相邻图像 · 仅定位，图像语义暂不可解释{neighbor.physical_page ? ` · 物理页 ${neighbor.physical_page}` : ""}</small><EvidencePointerDrawer label="定位相邻图像" onReturnToLearn={returnReaderSelection} pointerId={neighbor.evidence_pointer_id!} /></div>)}</article>)}</section> : <section className="learn-empty"><Icon icon="solar:book-2-linear" /><h2>从课程资料开始学习</h2><p>输入课程内的概念或问题，系统会先查找课程资料来源。</p></section>}</section><section className="learn-tutor"><header><div><h2>学习助手</h2><p>回答以当前课程资料为依据。</p></div><Icon icon="solar:chat-round-dots-linear" /></header><div className="learn-turns" aria-live="polite" aria-relevant="additions text">{visibleTurns.length ? visibleTurns.map((turn, index) => <article className={`learn-turn ${turn.role}`} key={index}><strong>{turn.role === "student" ? "我" : "学习助手"}</strong>{turn.explanation === "table" && <small className="table-explain-label">表格解释 · 来自已核验的表格引用</small>}<p>{turn.content || "正在整理检索来源…"}</p>{turn.status && <small className="learn-turn-status" role="status">{turn.status}</small>}{turn.citations.map((citation, citationIndex) => <div className="learn-citation" key={`${citation.pointerId ?? citation.label}-${citationIndex}`}><small><Icon icon="solar:book-bookmark-linear" />{materialTypeLabel(citation.materialType)} · {citation.label}</small><StudentProvenanceMetadata provenance={citation.provenance} />{citation.pointerId && <EvidencePointerDrawer label="打开引用" onReturnToLearn={returnReaderSelection} pointerId={citation.pointerId} />}</div>)}</article>) : <p className="empty-state">你可以围绕课程资料提问；证据不足时会明确说明。</p>}</div>{selectionContextPointerId && <div className="learn-selection-context"><span role="status" aria-live="polite">已将一个固定资料来源带回当前学习上下文。</span><EvidencePointerDrawer label="重新打开所选来源" onReturnToLearn={returnReaderSelection} pointerId={selectionContextPointerId} /><button type="button" onClick={clearReaderSelection}>清除选择</button></div>}{selectedTablePointer && <div className="selected-table-context" role="status" aria-live="polite"><strong>待解释的表格</strong><span>{selectedTablePointer.material_title}{selectedTablePointer.chapter_path ? ` · ${selectedTablePointer.chapter_path}` : ""}{selectedTablePointer.physical_page ? ` · 物理页 ${selectedTablePointer.physical_page}` : ""}</span><button type="button" disabled={sending} onClick={() => setSelectedTablePointer(null)}>移除</button></div>}{loadingTablePointer && <p className="status-banner" role="status">正在重新读取并校验表格引用…</p>}<form className="learn-composer" onSubmit={send}><input aria-label="围绕课程资料提问" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="围绕课程资料提问…" disabled={!materials.length || sending || restoreBlocked || loadingTablePointer} /><button type="submit" disabled={!materials.length || sending || restoreBlocked || loadingTablePointer} aria-label="发送问题"><Icon icon="solar:plain-2-bold" /></button></form></section></div></div>;}

export default function StudentLearnPage() {
  const { courseId } = useParams<{ courseId: string }>();
  return (
    <Suspense fallback={<p className="status-banner" role="status">正在读取学习空间…</p>}>
      <StudentLearnContent key={courseId} courseId={courseId} />
    </Suspense>
  );
}
