"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "../lib/api";
import {
  createMiniLab,
  getActiveMiniLab,
  invalidateMiniLab,
  listMiniLabs,
  saveMiniLabProgress,
  submitMiniLabResult,
  type MiniLabCatalogItem,
  type MiniLabSession,
} from "../lib/mini-lab-api";
import type { MiniLabResult } from "../lib/mini-lab/jspsych-adapter";
import MiniLabRuntime from "./learning/MiniLabRuntime";

const message = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "Mini Lab 暂时无法读取，请稍后重试。";

export default function StudentMiniLabPanel({ courseId }: { courseId: string }) {
  const [catalog, setCatalog] = useState<MiniLabCatalogItem[]>([]);
  const [selected, setSelected] = useState("");
  const [session, setSession] = useState<MiniLabSession | null>(null);
  const sessionRef = useRef<MiniLabSession | null>(null);
  const [notice, setNotice] = useState("正在读取可用实验…");
  const [busy, setBusy] = useState(false);
  const [recoveryGeneration, setRecoveryGeneration] = useState(0);
  const [invalidationReason, setInvalidationReason] = useState("");
  const pendingInvalidation = useRef<{ reason: string; key: string } | null>(null);

  useEffect(() => {
    if (!courseId) return;
    Promise.all([listMiniLabs(courseId), getActiveMiniLab(courseId)])
      .then(([items, active]) => {
        setCatalog(items);
        setSelected((current) => current || items[0]?.lab_key || "");
        sessionRef.current = active;
        setSession(active);
        setNotice(
          active?.status === "running"
            ? "已恢复上次未完成的实验，已保存阶段和答案均已保留。"
            : active?.status === "completed"
              ? "已恢复最近一次已提交记录。"
              : active?.status === "invalidated"
                ? "最近一次实验已作废，不能恢复或继续记录。"
            : items.length
              ? ""
              : "当前课程没有可用的 Mini Lab。",
        );
      })
      .catch((reason) => setNotice(message(reason)));
  }, [courseId]);

  async function start() {
    if (!selected) return;
    setBusy(true);
    try {
      const created = await createMiniLab(courseId, selected);
      sessionRef.current = created;
      setSession(created);
      setNotice("");
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  async function recover() {
    setBusy(true);
    try {
      const restored = await getActiveMiniLab(courseId);
      pendingInvalidation.current = null;
      sessionRef.current = restored;
      setSession(restored);
      setRecoveryGeneration((current) => current + 1);
      setNotice(
        restored?.status === "running"
          ? "已从服务端恢复最后一个已保存阶段；中断前未保存的试次不会计入记录。"
          : restored?.status === "completed"
            ? "服务端已确认实验完成，已恢复提交记录。"
            : "没有可恢复的实验会话。",
      );
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  const recordTrials = useCallback(async (trialData: MiniLabResult["trial_data"]) => {
    const current = sessionRef.current;
    if (!current) return;
    setBusy(true);
    try {
      const updated = await saveMiniLabProgress(current, trialData);
      sessionRef.current = updated;
      setSession(updated);
      setNotice("实验阶段已安全保存；刷新后可继续。");
    } catch (reason) {
      setNotice(message(reason));
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);

  const complete = useCallback(async (result: MiniLabResult) => {
    const current = sessionRef.current;
    if (!current) return;
    setBusy(true);
    try {
      const updated = await submitMiniLabResult(current, result);
      sessionRef.current = updated;
      setSession(updated);
      setNotice("实验记录已提交，等待服务端资格化。");
    } catch (reason) {
      setNotice(message(reason));
      throw reason;
    } finally {
      setBusy(false);
    }
  }, []);

  async function invalidate() {
    const current = sessionRef.current;
    const reason = invalidationReason.trim();
    if (!current || current.status !== "running" || !reason) return;
    setBusy(true);
    try {
      const pending = pendingInvalidation.current?.reason === reason
        ? pendingInvalidation.current
        : { reason, key: `mini-lab:${current.id}:${crypto.randomUUID()}` };
      pendingInvalidation.current = pending;
      const invalidated = await invalidateMiniLab(current, reason, pending.key);
      pendingInvalidation.current = null;
      sessionRef.current = invalidated;
      setSession(invalidated);
      setNotice("实验会话已作废；已保存阶段保留为记录，但不会生成完成资格。");
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setBusy(false);
    }
  }

  const definition = session?.definition_snapshot;
  return (
    <section className="support-panel mini-lab-panel">
      <div className="panel-heading">
        <div><h2>Mini Lab 实验学习</h2><p>完成预测、观察、解释和迁移总结，形成可追溯的 transfer 证据。</p></div>
        {session && <span>{session.status === "completed" ? "已提交" : session.status === "invalidated" ? "已作废" : "进行中"}</span>}
      </div>
      {notice && <p className="status-banner" role="status" aria-live="polite">{notice}</p>}
      {!session ? (
        <div className="mini-lab-start">
          <label className="field-label">选择实验<select value={selected} onChange={(event) => setSelected(event.target.value)} disabled={!catalog.length}>
            {catalog.map((item) => <option key={item.lab_key} value={item.lab_key}>{item.title}{item.source_status === "engineering_fixture" ? "（工程 fixture）" : ""}</option>)}
          </select></label>
          {catalog.find((item) => item.lab_key === selected)?.source_note && <p role="note">{catalog.find((item) => item.lab_key === selected)?.source_note}</p>}
          <button className="primary-button" disabled={busy || !selected} onClick={() => void start()}>开始 Mini Lab</button>
        </div>
      ) : session.status === "completed" ? (
        <div className="case-result"><strong>实验记录已保存</strong><p>资格化状态：{session.derived_measure?.qualification_status ?? "pending"}</p><button className="secondary-button" onClick={() => { sessionRef.current = null; setSession(null); }}>开始新实验</button></div>
      ) : session.status === "invalidated" ? (
        <div className="case-result" data-lab-status="invalidated"><strong>实验已作废</strong><p>作废理由：{session.invalidation_reason ?? "未提供"}</p><p>该会话不能恢复、续写、提交或获得资格化。</p><button className="secondary-button" type="button" onClick={() => { sessionRef.current = null; setSession(null); setInvalidationReason(""); }}>开始新实验</button></div>
      ) : definition ? <>
        {definition.source_status === "engineering_fixture" && <p className="status-banner" role="note">工程 fixture：{definition.source_note ?? "并非基于已获准教材的正式实验定义。"}</p>}
        <div className="mini-lab-invalidation">
          <label className="field-label" htmlFor="mini-lab-invalidation-reason">作废理由
            <textarea id="mini-lab-invalidation-reason" value={invalidationReason} onChange={(event) => setInvalidationReason(event.target.value)} maxLength={500} rows={2} disabled={busy} />
          </label>
          <button className="secondary-button" type="button" onClick={() => void invalidate()} disabled={busy || !invalidationReason.trim()}>作废当前实验</button>
        </div>
        <MiniLabRuntime key={`${session.id}:${recoveryGeneration}`} definition={definition} initialTrialData={session.trial_data} onTrial={recordTrials} onComplete={complete} onRecover={recover} />
      </> : <p className="empty-state">实验定义不可用。</p>}
    </section>
  );
}
