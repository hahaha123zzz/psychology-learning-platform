"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "../lib/api";

type CaseCatalogItem = {
  case_key: string;
  title: string;
  case_kind?: string;
  knowledge_point?: string;
};
type CaseSession = {
  id: string;
  course_id: string;
  status: string;
  case_key: string;
  case_snapshot: {
    title: string;
    prompt: string;
    options: { key: string; label: string }[];
  };
  response: {
    selected_confound: string;
    reasoning: string;
    design_change: string;
  } | null;
  outcome: {
    points: number;
    max_points: number;
    feedback: string;
    qualification_status: string;
    components?: {
      selection_points: number;
      reasoning_completion_points?: number;
      reasoning_points?: number;
      design_completion_points: number;
    };
  } | null;
  version: number;
};

const message = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "案例工作区暂时无法读取。";

export default function StudentCaseWorkbench() {
  const courseId =
    typeof window === "undefined"
      ? ""
      : new URLSearchParams(window.location.search).get("course_id") ?? "";
  const [catalog, setCatalog] = useState<CaseCatalogItem[]>([]);
  const [caseKey, setCaseKey] = useState("confound-basic");
  const [, setItems] = useState<CaseSession[]>([]);
  const [current, setCurrent] = useState<CaseSession | null>(null);
  const [selected, setSelected] = useState("");
  const [reasoning, setReasoning] = useState("");
  const [designChange, setDesignChange] = useState("");
  const [notice, setNotice] = useState("请从课程学习空间进入案例推理。");
  const [busy, setBusy] = useState(false);
  const [draftState, setDraftState] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [failedAction, setFailedAction] = useState<"draft" | "submit" | null>(null);
  const [versionConflict, setVersionConflict] = useState(false);
  const [lockedElsewhere, setLockedElsewhere] = useState(false);
  const [workspaceLoaded, setWorkspaceLoaded] = useState(false);
  const [workspaceFailed, setWorkspaceFailed] = useState(false);
  const [loadAttempt, setLoadAttempt] = useState(0);

  useEffect(() => {
    if (!courseId) return;
    let active = true;
    Promise.allSettled([
      api<CaseCatalogItem[]>("/student/cases/catalog"),
      api<CaseSession[]>(`/student/cases?course_id=${courseId}`),
    ])
      .then(([catalogResult, sessionsResult]) => {
        if (!active) return;
        const errors: unknown[] = [];
        if (catalogResult.status === "fulfilled") {
          setCatalog(catalogResult.value);
        } else {
          errors.push(catalogResult.reason);
        }
        if (sessionsResult.status === "fulfilled") {
          const nextItems = sessionsResult.value;
          setItems(nextItems);
          const resumable =
            nextItems.find((item) => item.status === "active") ?? nextItems[0];
          if (resumable) {
            setCurrent(resumable);
            setCaseKey(resumable.case_key);
            setSelected(resumable.response?.selected_confound ?? "");
            setReasoning(resumable.response?.reasoning ?? "");
            setDesignChange(resumable.response?.design_change ?? "");
            setDraftState(resumable.response ? "saved" : "idle");
          }
        } else {
          errors.push(sessionsResult.reason);
        }
        setWorkspaceFailed(errors.length > 0);
        setWorkspaceLoaded(errors.length === 0);
        setNotice(errors.length ? errors.map(message).join("；") : "");
      })
      .catch((reason) => {
        if (!active) return;
        setWorkspaceFailed(true);
        setWorkspaceLoaded(false);
        setNotice(message(reason));
      });
    return () => { active = false; };
  }, [courseId, loadAttempt]);

  function retryWorkspaceLoad() {
    setWorkspaceFailed(false);
    setNotice("正在重新读取案例与已有会话…");
    setLoadAttempt((attempt) => attempt + 1);
  }

  async function start() {
    if (!courseId) return;
    setBusy(true);
    try {
      const next = await api<CaseSession>("/student/cases", {
        method: "POST",
        body: JSON.stringify({ course_id: courseId, case_key: caseKey }),
      });
      setItems((all) => [next, ...all]);
      setCurrent(next);
      setSelected("");
      setReasoning("");
      setDesignChange("");
      setDraftState("idle");
      setFailedAction(null);
      setVersionConflict(false);
      setLockedElsewhere(false);
      setNotice("");
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function saveDraft() {
    if (!current || current.status !== "active" || lockedElsewhere) return;
    setBusy(true);
    setDraftState("saving");
    setVersionConflict(false);
    try {
      const next = await api<CaseSession>(`/student/cases/${current.id}/respond`, {
        method: "POST",
        body: JSON.stringify({
          version: current.version,
          draft: true,
          selected_confound: selected,
          reasoning,
          design_change: designChange,
        }),
      });
      setCurrent(next);
      setItems((all) => all.map((item) => (item.id === next.id ? next : item)));
      setDraftState("saved");
      setFailedAction(null);
      setNotice("草稿已保存；刷新后可从同一案例会话恢复。");
    } catch (reason) {
      setDraftState("error");
      setFailedAction("draft");
      setVersionConflict(reason instanceof ApiError && reason.status === 409);
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function refreshDraftVersion() {
    if (!current) return;
    setBusy(true);
    try {
      const latest = await api<CaseSession>(`/student/cases/${current.id}`);
      if (latest.status !== "active") {
        setLockedElsewhere(true);
        setVersionConflict(false);
        setNotice("此案例已在其他位置提交；当前未保存输入仍保留，但不能覆盖已提交版本。");
        return;
      }
      setCurrent(latest);
      setItems((all) => all.map((item) => (item.id === latest.id ? latest : item)));
      setVersionConflict(false);
      setDraftState("idle");
      setFailedAction(null);
      setNotice("已更新服务端草稿版本；当前输入已保留，可重试保存。");
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function submit() {
    if (!current) return;
    setBusy(true);
    setVersionConflict(false);
    try {
      const next = await api<CaseSession>(
        `/student/cases/${current.id}/respond`,
        {
          method: "POST",
          body: JSON.stringify({
            version: current.version,
            selected_confound: selected,
            reasoning,
            design_change: designChange,
          }),
        },
      );
      setCurrent(next);
      setItems((all) => all.map((item) => (item.id === next.id ? next : item)));
      setDraftState("saved");
      setFailedAction(null);
      setNotice("案例作答已保存；资格化状态由服务端后续处理。");
    } catch (reason) {
      setDraftState("error");
      setFailedAction("submit");
      setVersionConflict(reason instanceof ApiError && reason.status === 409);
      try {
        const latest = await api<CaseSession>(`/student/cases/${current.id}`);
        if (latest.status === "completed") {
          setCurrent(latest);
          setItems((all) => all.map((item) => (item.id === latest.id ? latest : item)));
          setSelected(latest.response?.selected_confound ?? "");
          setReasoning(latest.response?.reasoning ?? "");
          setDesignChange(latest.response?.design_change ?? "");
          setFailedAction(null);
          setNotice("服务器已保存此案例；已恢复服务端提交结果。");
        } else if (latest.version !== current.version) {
          setCurrent(latest);
          setItems((all) => all.map((item) => (item.id === latest.id ? latest : item)));
          setVersionConflict(true);
          setNotice("案例版本已变化；当前输入仍保留，请刷新版本后再提交。");
        } else {
          setNotice(`${message(reason)} 当前输入仍保留，可重试提交。`);
        }
      } catch {
        setNotice(`${message(reason)} 当前输入仍保留；网络恢复后可重试提交。`);
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="functional-app">
      <header className="app-header">
        <strong>实验推理工作区</strong>
        <span>选择—解释—设计调整</span>
      </header>
      <section className="student-support-page">
        {notice && <p className="status-banner" role={draftState === "error" || workspaceFailed ? "alert" : "status"}>{notice}</p>}
        {!courseId ? (
          <p className="empty-state">请从具体课程进入案例推理。</p>
        ) : !workspaceLoaded ? (
          <section className="support-panel" aria-busy={!workspaceFailed}>
            <h1>{workspaceFailed ? "暂时无法读取案例工作区" : "正在读取案例工作区…"}</h1>
            <p className="empty-state">{workspaceFailed ? "尚未确认当前课程已有的案例会话；读取成功前不能开始新案例。" : "正在读取案例目录和已有会话。"}</p>
            {workspaceFailed && <button className="secondary-button" type="button" onClick={retryWorkspaceLoad}>重试读取案例</button>}
          </section>
        ) : !current ? (
          <section className="support-panel">
            <h1>实验推理案例</h1>
            <p>选择案例类型，再用文字解释和设计调整形成可验证的推理证据。</p>
            <label className="field-label">
              案例类型
              <select value={caseKey} onChange={(event) => setCaseKey(event.target.value)}>
                {(catalog.length
                  ? catalog
                  : [{ case_key: "confound-basic", title: "找出混淆变量" }]
                ).map((item) => (
                  <option key={item.case_key} value={item.case_key}>
                    {item.title}
                  </option>
                ))}
              </select>
            </label>
            <button className="primary-button" disabled={busy} onClick={() => void start()}>
              开始案例
            </button>
          </section>
        ) : (
          <section className="support-panel">
            <div className="panel-heading">
              <h1>{current.case_snapshot.title}</h1>
              <span>{current.status === "completed" ? "已提交" : "进行中"}</span>
            </div>
            <p className="case-prompt">{current.case_snapshot.prompt}</p>
            {current.status === "active" ? (
              <>
                <p id="case-response-help" className="empty-state">
                  按顺序完成选择、理由和设计调整。结果仅反馈填写完整度，不评价推理正确性；题面和选项可随时回看。
                </p>
                <fieldset className="case-options" disabled={busy || lockedElsewhere}>
                  <legend>选择最关键的变量或设计问题</legend>
                  {current.case_snapshot.options.map((option) => (
                    <label key={option.key}>
                      <input
                        type="radio"
                        name="case-option"
                        value={option.key}
                        checked={selected === option.key}
                        onChange={() => {
                          setSelected(option.key);
                          setDraftState("idle");
                        }}
                      />
                      {option.label}
                    </label>
                  ))}
                </fieldset>
                <label className="field-label" style={{ display: "grid", minWidth: 0, gap: "0.45rem" }}>
                  为什么它会影响结论
                  <textarea
                    style={{ display: "block", width: "100%", minWidth: 0, minHeight: "8rem", boxSizing: "border-box" }}
                    value={reasoning}
                    aria-describedby="case-response-help"
                    maxLength={2000}
                    readOnly={lockedElsewhere}
                    onChange={(event) => {
                      setReasoning(event.target.value);
                      setDraftState("idle");
                    }}
                    minLength={1}
                  />
                </label>
                <label className="field-label" style={{ display: "grid", minWidth: 0, gap: "0.45rem" }}>
                  如何调整实验设计
                  <textarea
                    style={{ display: "block", width: "100%", minWidth: 0, minHeight: "8rem", boxSizing: "border-box" }}
                    value={designChange}
                    aria-describedby="case-response-help"
                    maxLength={2000}
                    readOnly={lockedElsewhere}
                    onChange={(event) => {
                      setDesignChange(event.target.value);
                      setDraftState("idle");
                    }}
                    minLength={1}
                  />
                </label>
                <div className="attempt-actions">
                  <button className="secondary-button" disabled={busy || lockedElsewhere} onClick={() => void saveDraft()}>
                    {draftState === "error" ? "重试保存草稿" : "保存草稿"}
                  </button>
                  {versionConflict && <button className="secondary-button" disabled={busy} onClick={() => void refreshDraftVersion()}>刷新版本并保留当前输入</button>}
                  {failedAction === "submit" && <button className="secondary-button" disabled={busy || lockedElsewhere} onClick={() => void submit()}>重试提交</button>}
                  <button
                    className="primary-button"
                    disabled={busy || lockedElsewhere || !selected || !reasoning.trim() || !designChange.trim()}
                    onClick={() => void submit()}
                  >
                    提交案例推理
                  </button>
                </div>
                {draftState !== "idle" && <small role="status">{draftState === "saving" ? "正在保存草稿…" : draftState === "saved" ? "草稿已保存" : failedAction === "submit" ? "提交尚未确认；输入仍保留，可安全重试或刷新版本。" : "草稿保存失败；输入仍保留，可重试或刷新版本。"}</small>}
              </>
            ) : (
              <div className="case-result">
                <strong>
                  {current.outcome?.points ?? 0} / {current.outcome?.max_points ?? 3}
                </strong>
                <p>{current.outcome?.feedback}</p>
                {current.outcome?.components && <small>填写完整度：选择 {current.outcome.components.selection_points} 项 · 理由 {(current.outcome.components.reasoning_completion_points ?? current.outcome.components.reasoning_points ?? 0) ? "达到完整度要求" : "仍可补充"} · 设计说明 {current.outcome.components.design_completion_points ? "达到完整度要求" : "仍可补充"}</small>}
                <small>此结果不判断答案正确性或推理质量。</small>
                <small>资格化状态：{current.outcome?.qualification_status}</small>
                <button className="secondary-button" onClick={() => setCurrent(null)}>
                  开始新案例
                </button>
              </div>
            )}
          </section>
        )}
      </section>
    </main>
  );
}
