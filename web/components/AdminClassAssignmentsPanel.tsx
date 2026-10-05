"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import {
  assignAdminClassTeacher,
  adminOperationKey,
  clearAdminOperationKey,
  endAdminClassTeacherAssignment,
  getAdminClassAssignmentOptions,
  listRoleAssignmentCourses,
  type AdminClassAssignment,
  type AdminClassAssignmentOptions,
  type CourseScopeOption,
  type AdminOperationKeyCache,
} from "../lib/admin-api";
import AdminConfirmationDialog from "./AdminConfirmationDialog";
import AdminCourseGovernancePanel from "./AdminCourseGovernancePanel";
import { useAdminWriteGate } from "../app/admin/useAdminWriteGate";

const explain = (reason: unknown) => reason instanceof ApiError ? reason.message : "任课管理操作失败，请刷新后重试。";
const conflictText = (error: unknown) => error instanceof ApiError && error.status === 409
  ? "任课记录已被其他操作更新（409）；已重新读取课程状态，请核对最新版本后再继续。"
  : explain(error);
type PendingAction =
  | { kind: "assign"; input: { class_id: string; teacher_id: string; assignment_role: "lead" | "assistant"; reason: string }; summary: string }
  | { kind: "end"; item: AdminClassAssignment; reason: string; summary: string };

function AdminTeacherAssignmentsPanel() {
  const operationKeys = useRef<AdminOperationKeyCache>(new Map());
  const optionsRequestVersion = useRef(0);
  const { canWrite, viewportReady, isNarrow } = useAdminWriteGate();
  const [courses, setCourses] = useState<CourseScopeOption[]>([]);
  const [courseId, setCourseId] = useState("");
  const [options, setOptions] = useState<AdminClassAssignmentOptions | null>(null);
  const [classId, setClassId] = useState("");
  const [teacherId, setTeacherId] = useState("");
  const [assignmentRole, setAssignmentRole] = useState<"lead" | "assistant">("lead");
  const [reason, setReason] = useState("");
  const [endReasons, setEndReasons] = useState<Record<string, string>>({});
  const [notice, setNotice] = useState("正在读取同机构课程…");
  const [noticeIsError, setNoticeIsError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loadingCourses, setLoadingCourses] = useState(true);
  const [loadingOptions, setLoadingOptions] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);

  const loadOptions = useCallback(async (selectedCourseId: string) => {
    if (!selectedCourseId) return false;
    const requestVersion = ++optionsRequestVersion.current;
    setLoadingOptions(true);
    setOptions(null);
    try {
      const next = await getAdminClassAssignmentOptions(selectedCourseId);
      if (requestVersion !== optionsRequestVersion.current) return false;
      setOptions(next);
      setClassId((current) => next.classes.some((item) => item.id === current) ? current : "");
      setTeacherId((current) => next.teachers.some((item) => item.id === current) ? current : "");
      setNotice("");
      setNoticeIsError(false);
      return true;
    } catch (error) {
      if (requestVersion === optionsRequestVersion.current) {
        setOptions(null);
        setNotice(explain(error));
        setNoticeIsError(true);
      }
      return false;
    } finally {
      if (requestVersion === optionsRequestVersion.current) setLoadingOptions(false);
    }
  }, []);

  useEffect(() => {
    let active = true;
    listRoleAssignmentCourses()
      .then((next) => {
        if (!active) return;
        setCourses(next);
        setLoadingCourses(false);
        const initialCourseId = next[0]?.id ?? "";
        setCourseId((current) => current || initialCourseId);
        if (initialCourseId) void loadOptions(initialCourseId);
        else { setNotice("当前机构没有可管理课程。"); setNoticeIsError(false); }
      })
      .catch((error) => {
        if (active) { setLoadingCourses(false); setNotice(explain(error)); setNoticeIsError(true); }
      });
    return () => { active = false; optionsRequestVersion.current += 1; };
  }, [loadOptions]);
  useEffect(() => {
    const membershipChanged = (event: Event) => {
      const detail = (event as CustomEvent<{ courseId?: string }>).detail;
      if (detail?.courseId === courseId) void loadOptions(courseId);
    };
    window.addEventListener("admin-course-membership-changed", membershipChanged);
    return () => window.removeEventListener("admin-course-membership-changed", membershipChanged);
  }, [courseId, loadOptions]);
  useEffect(() => {
    if (canWrite) return;
    const timer = window.setTimeout(() => setPending(null), 0);
    return () => window.clearTimeout(timer);
  }, [canWrite]);

  function requestAssignment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanReason = reason.trim();
    if (!canWrite || !classId || !teacherId || cleanReason.length < 8) return;
    const selectedClass = options?.classes.find((item) => item.id === classId);
    const selectedTeacher = options?.teachers.find((item) => item.id === teacherId);
    const input = { class_id: classId, teacher_id: teacherId, assignment_role: assignmentRole, reason: cleanReason };
    setPending({
      kind: "assign", input,
      summary: `将 ${selectedTeacher?.display_name ?? teacherId} 分配到「${selectedClass?.code ?? ""} ${selectedClass?.name ?? classId}」，职责为${assignmentRole === "lead" ? "主负责人" : "协助教师"}。`,
    });
  }

  function requestEnd(item: AdminClassAssignment, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanReason = endReasons[item.id]?.trim() ?? "";
    if (!canWrite || cleanReason.length < 8 || item.status !== "active") return;
    setPending({
      kind: "end", item, reason: cleanReason,
      summary: `结束 ${item.teacher_name} 在「${item.class_code} ${item.class_name}」的${item.assignment_role === "lead" ? "主负责人" : "协助教师"}任课关系（当前版本 v${item.version}）。`,
    });
  }

  async function confirmPending() {
    if (!pending || !canWrite || busy) return;
    setBusy(true);
    try {
      let receipt: string;
      if (pending.kind === "assign") {
        const { input } = pending;
        const result = await assignAdminClassTeacher(input, adminOperationKey(operationKeys.current, "assign", input));
        clearAdminOperationKey(operationKeys.current, "assign");
        setReason("");
        receipt = `任课关系已生效：记录 ${result.id} · v${result.version} · ${result.status}。`;
      } else {
        const { item, reason: endReason } = pending;
        const input = { version: item.version, reason: endReason };
        const operation = `end:${item.id}`;
        const result = await endAdminClassTeacherAssignment(item.id, item.version, endReason, adminOperationKey(operationKeys.current, operation, input));
        clearAdminOperationKey(operationKeys.current, operation);
        setEndReasons((current) => ({ ...current, [item.id]: "" }));
        receipt = `任课关系已结束：记录 ${result.id} · v${result.version} · ${result.status}；班级级权限将按最新 Scope 重新判断。`;
      }
      setPending(null);
      await loadOptions(courseId);
      setNotice(receipt);
      setNoticeIsError(false);
    } catch (error) {
      setPending(null);
      const refreshed = await loadOptions(courseId);
      setNotice(`${conflictText(error)}${refreshed ? " 当前课程状态已刷新；请核对后再操作。" : " 状态刷新失败，请先重试刷新。"}`);
      setNoticeIsError(true);
    } finally { setBusy(false); }
  }

  return <section className="data-panel">
    <div className="panel-heading">
      <div><h2>班级任课治理</h2><p>管理员只能管理本机构课程；任课对象必须已是该课程的教师或助教成员。</p></div>
      <button className="secondary-button" type="button" disabled={!courseId || loadingOptions} onClick={() => void loadOptions(courseId)}>刷新</button>
    </div>
    {notice && <p className="status-banner" role={noticeIsError ? "alert" : "status"}>{notice}</p>}
    {viewportReady && isNarrow && <p className="status-banner" role="status">窄屏只读：任课分配/结束属于高影响操作，请使用宽屏；本页仍可查看课程和现有任课记录。</p>}
    <p className="empty-state">课程成员与班级学生成员由上方独立管理员入口维护；此区域仅使用 TeacherAssignment 维护任课关系，不会把管理员身份变成教学身份。</p>
    {loadingCourses && <p className="status-banner" role="status">正在读取本机构课程…</p>}
    {courses.length > 0 && <label className="admin-class-course-select">课程<select value={courseId} disabled={busy || loadingOptions} onChange={(event) => { const nextCourseId = event.target.value; setCourseId(nextCourseId); void loadOptions(nextCourseId); }}>
      {courses.map((course) => <option key={course.id} value={course.id}>{course.title} · {course.term}</option>)}
    </select></label>}
    {loadingOptions && <p className="empty-state" role="status">正在读取所选课程的班级、已入课教师/助教和任课记录…</p>}
    {options && <>
      {canWrite ? <form className="stack-form" onSubmit={requestAssignment}>
        <h3>分配任课教师</h3>
        {options.classes.length ? <label>班级<select value={classId} onChange={(event) => setClassId(event.target.value)} required><option value="">选择班级</option>{options.classes.map((item) => <option key={item.id} value={item.id}>{item.code} · {item.name}</option>)}</select></label> : <p className="empty-state">该课程暂无可管理班级。</p>}
        {options.teachers.length ? <label>课程教师/助教<select value={teacherId} onChange={(event) => setTeacherId(event.target.value)} required><option value="">选择已加入课程的成员</option>{options.teachers.map((item) => <option key={item.id} value={item.id}>{item.display_name} · {item.course_role === "teacher" ? "课程教师" : "课程助教"}</option>)}</select></label> : <p className="empty-state">当前课程没有已加入的教师/助教成员；请先通过受控成员管理入口完成入课。</p>}
        <label>班级职责<select value={assignmentRole} onChange={(event) => setAssignmentRole(event.target.value as typeof assignmentRole)}><option value="lead">主负责人</option><option value="assistant">协助教师</option></select></label>
        <label>分配理由（必填，至少 8 个字符）<textarea value={reason} onChange={(event) => setReason(event.target.value)} minLength={8} maxLength={500} required /></label>
        <button className="primary-button" type="submit" disabled={busy || !classId || !teacherId || reason.trim().length < 8}>检查并复核分配</button>
        <small>复核将再次展示班级、教师、职责和理由；操作写入理由审计与 Outbox，不会把管理员身份转换为教师权限。</small>
      </form> : !viewportReady && <p className="status-banner" role="status">正在确认屏幕尺寸；写操作暂不可用。</p>}
      <div className="panel-heading"><h3>班级任课记录</h3></div>
      {options.assignments.length ? options.assignments.map((item) => <article className="question-card" key={item.id}>
        <div><strong>{item.class_code} · {item.class_name} — {item.teacher_name}</strong><small>{item.assignment_role === "lead" ? "主负责人" : "协助教师"} · {item.status === "active" ? "有效" : "已结束"} · v{item.version}</small></div>
        {item.status === "active" && canWrite && <details><summary>结束任课</summary><form className="stack-form" onSubmit={(event) => requestEnd(item, event)}><label>结束理由（必填，至少 8 个字符）<textarea value={endReasons[item.id] ?? ""} onChange={(event) => setEndReasons((current) => ({ ...current, [item.id]: event.target.value }))} minLength={8} maxLength={500} required /></label><button className="secondary-button" type="submit" disabled={busy || (endReasons[item.id]?.trim().length ?? 0) < 8}>复核后结束</button></form></details>}
      </article>) : <p className="empty-state">当前课程暂无任课记录。</p>}
    </>}
    <AdminConfirmationDialog
      open={Boolean(pending)}
      title={pending?.kind === "assign" ? "复核班级任课分配" : "复核结束任课关系"}
      summary={pending?.summary ?? ""}
      impact="此操作仅变更独立 TeacherAssignment 关系；不会创建/删除课程成员，也不会授予平台管理员隐式教师权限。服务端会按机构与课程 Scope 校验。"
      reason={pending?.kind === "assign" ? pending.input.reason : pending?.reason ?? ""}
      confirmLabel={pending?.kind === "assign" ? "确认分配" : "确认结束"}
      busy={busy}
      onConfirm={() => void confirmPending()}
      onCancel={() => setPending(null)}
    />
  </section>;
}

export default function AdminClassAssignmentsPanel() {
  return <>
    <AdminCourseGovernancePanel />
    <AdminTeacherAssignmentsPanel />
  </>;
}
