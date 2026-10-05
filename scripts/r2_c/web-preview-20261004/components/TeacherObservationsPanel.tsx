"use client";

import { FormEvent, useCallback, useEffect, useRef, useState } from "react";
import {
  createTeacherObservation,
  listTeacherObservationRevalidationCandidates,
  listTeacherObservations,
  revalidateTeacherObservation,
  reviewTeacherObservation,
  type TeacherObservation,
  type TeacherObservationRevalidationCandidate,
} from "../lib/interventions-api";
import { ApiError, idempotencyKey } from "../lib/api";

const message = (reason: unknown) =>
  reason instanceof ApiError ? reason.message : "教师观察暂时无法保存，请稍后重试。";

const qualificationLabel: Record<TeacherObservation["verification_status"], string> = {
  pending: "待独立再验证",
  qualified: "已通过独立再验证",
  rejected: "未通过复核",
  invalidated: "再验证证据已失效",
};

const reviewLabel: Record<TeacherObservation["review_decision"], string> = {
  pending: "待教师复核",
  accepted: "教师复核通过",
  rejected: "教师复核拒绝",
};

export default function TeacherObservationsPanel({ courseId }: { courseId: string }) {
  const [items, setItems] = useState<TeacherObservation[]>([]);
  const [notice, setNotice] = useState("正在读取教师观察…");
  const createRequestKey = useRef<string | null>(null);
  const [candidates, setCandidates] = useState<Record<string, TeacherObservationRevalidationCandidate[]>>({});
  const [loadingCandidates, setLoadingCandidates] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await listTeacherObservations(courseId);
      setItems(next);
      setNotice("");
    } catch (reason) {
      setNotice(message(reason));
    }
  }, [courseId]);

  useEffect(() => {
    const timer = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(timer);
  }, [load]);

  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const formElement = event.currentTarget;
    const form = new FormData(formElement);
    const requestKey = createRequestKey.current ?? idempotencyKey();
    createRequestKey.current = requestKey;
    try {
      await createTeacherObservation(courseId, {
        student_id: String(form.get("student_id")),
        class_id: String(form.get("class_id")),
        observation_type: String(form.get("observation_type")) as TeacherObservation["observation_type"],
        note: String(form.get("note")),
        evidence_refs: String(form.get("evidence_refs") ?? "")
          .split(",")
          .map((value) => value.trim())
          .filter(Boolean),
      }, requestKey);
      formElement.reset();
      createRequestKey.current = null;
      setNotice("观察已保存为待复核记录，不会直接改变学生掌握状态。");
      await load();
    } catch (reason) {
      setNotice(message(reason));
    }
  }

  async function revalidate(event: FormEvent<HTMLFormElement>, item: TeacherObservation) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    try {
      const next = await revalidateTeacherObservation(
        courseId,
        item,
        String(form.get("learning_event_id")),
      );
      setItems((all) => all.map((current) => (current.id === next.id ? next : current)));
      setCandidates((all) => ({ ...all, [item.id]: [] }));
      setNotice("独立再验证已关联现有资格化证据；复核没有重复写入学习证据。 ");
    } catch (reason) {
      setNotice(message(reason));
    }
  }

  async function loadCandidates(item: TeacherObservation) {
    setLoadingCandidates(item.id);
    try {
      const next = await listTeacherObservationRevalidationCandidates(courseId, item.id);
      setCandidates((all) => ({ ...all, [item.id]: next }));
      setNotice(next.length ? "已读取学生在观察之后完成并通过资格化的独立活动。" : "当前没有符合条件的独立再验证活动。");
    } catch (reason) {
      setNotice(message(reason));
    } finally {
      setLoadingCandidates(null);
    }
  }

  async function review(item: TeacherObservation, decision: "qualified" | "rejected") {
    try {
      const next = await reviewTeacherObservation(
        courseId,
        item,
        decision,
        decision === "qualified" ? "教师复核确认，仍需独立学习证据验证" : "证据不足，暂不纳入资格化",
      );
      setItems((all) => all.map((current) => (current.id === next.id ? next : current)));
      setNotice(decision === "qualified" ? "教师复核已通过；记录仍待独立再验证，不会据此生成学习证据。" : "观察已标记为不合格。");
    } catch (reason) {
      setNotice(message(reason));
    }
  }

  return (
    <section className="support-panel teacher-list">
      <div className="panel-heading">
        <div>
          <h2>教师观察与异议</h2>
          <p>观察先保持待复核；教师接受异议后仍需独立再验证。复核不会覆盖原始作答或直接修改掌握度。</p>
          <p>仅当前课程有权限的教师和助教可见；在可见性政策明确前，不向学生展示观察正文。</p>
        </div>
        <span>{items.length} 条</span>
      </div>
      {notice && <p className="status-banner">{notice}</p>}
      <form
        className="support-form"
        onSubmit={create}
        onChange={() => { createRequestKey.current = null; }}
      >
        <input name="class_id" placeholder="班级 ID" required />
        <input name="student_id" placeholder="学生 ID" required />
        <select name="observation_type" defaultValue="misconception">
          <option value="misconception">误区</option>
          <option value="strategy">策略</option>
          <option value="support_need">支持需求</option>
          <option value="progress">进展</option>
        </select>
        <textarea name="note" placeholder="基于课堂或作答证据记录观察" required />
        <input name="evidence_refs" placeholder="有效学习证据 ID（逗号分隔，必填）" required />
        <button className="primary-button">保存待复核观察</button>
      </form>
      {items.length ? (
        items.map((item) => (
          <article className="teacher-row" key={item.id}>
            <div>
              <span className={`status-tag ${item.verification_status}`}>{qualificationLabel[item.verification_status]}</span>
              <small>{reviewLabel[item.review_decision]}</small>
              <strong>{item.student_id} · {item.observation_type}</strong>
              <small>{item.note}</small>
              {item.source_evidence_status !== "valid" && (
                <small>原观察来源已失效或不可用，历史记录仍保留。</small>
              )}
              {item.review_decision === "accepted" && item.verification_status === "pending" && (
                candidates[item.id] ? (
                  candidates[item.id].length ? (
                    <form className="support-form" onSubmit={(event) => void revalidate(event, item)}>
                      <select name="learning_event_id" required defaultValue="">
                        <option value="" disabled>选择已资格化的独立活动</option>
                        {candidates[item.id].map((candidate) => (
                          <option key={candidate.learning_event_id} value={candidate.learning_event_id}>
                            {candidate.event_type} · {candidate.source_type} · {new Date(candidate.occurred_at).toLocaleString()} · {candidate.evidence_count} 条证据
                          </option>
                        ))}
                      </select>
                      <button className="primary-button">关联再验证</button>
                    </form>
                  ) : (
                    <small>目前没有符合条件的独立再验证活动。</small>
                  )
                ) : (
                  <button
                    className="secondary-button"
                    onClick={() => void loadCandidates(item)}
                    disabled={loadingCandidates === item.id}
                  >
                    {loadingCandidates === item.id ? "正在读取…" : "读取可用的再验证活动"}
                  </button>
                )
              )}
            </div>
            {item.qualification_status === "pending" && item.review_decision === "pending" && (
              <div className="button-row">
                <button className="secondary-button" onClick={() => void review(item, "rejected")}>保留异议</button>
                <button className="primary-button" onClick={() => void review(item, "qualified")}>确认复核</button>
              </div>
            )}
          </article>
        ))
      ) : (
        <p className="empty-state">当前课程没有教师观察。</p>
      )}
    </section>
  );
}
