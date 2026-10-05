"use client";

import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError } from "../lib/api";
import {
  addAdminClassMember,
  addAdminCourseMember,
  adminOperationKey,
  clearAdminOperationKey,
  createAdminClass,
  listAdminClassMembers,
  listAdminClasses,
  listAdminCourseMembers,
  listAdminCourses,
  removeAdminClassMember,
  removeAdminCourseMember,
  searchRoleAssignmentTargets,
  type AdminClassMember,
  type AdminCourse,
  type AdminCourseMember,
  type AdminGovernedClass,
  type AdminOperationKeyCache,
  type RoleAssignmentTarget,
} from "../lib/admin-api";
import AdminConfirmationDialog from "./AdminConfirmationDialog";
import { useAdminWriteGate } from "../app/admin/useAdminWriteGate";

const explain = (error: unknown) => error instanceof ApiError ? error.message : "课程治理操作失败，请刷新后重试。";
const explainConflict = (error: unknown) => error instanceof ApiError && error.status === 409
  ? "记录版本已变化（409）；列表已刷新，请核对最新状态和版本后重新发起操作。"
  : explain(error);
type PendingAction =
  | { kind: "create-class"; courseId: string; input: { code: string; name: string; reason: string }; summary: string }
  | { kind: "add-course-member"; courseId: string; input: { user_id: string; role: AdminCourseMember["role"]; reason: string }; summary: string }
  | { kind: "remove-course-member"; courseId: string; item: AdminCourseMember; reason: string; summary: string }
  | { kind: "add-class-member"; classId: string; input: { user_id: string; reason: string }; summary: string }
  | { kind: "remove-class-member"; classId: string; item: AdminClassMember; reason: string; summary: string };

function TargetPicker({ label, value, onSelect }: { label: string; value: string; onSelect: (id: string) => void }) {
  const requestVersion = useRef(0);
  const [query, setQuery] = useState("");
  const [targets, setTargets] = useState<RoleAssignmentTarget[]>([]);
  const [state, setState] = useState<"idle" | "loading" | "results" | "empty" | "error">("idle");
  useEffect(() => {
    const current = ++requestVersion.current;
    const cleanQuery = query.trim();
    if (cleanQuery.length < 3) { setTargets([]); setState("idle"); return; }
    setState("loading");
    const timer = window.setTimeout(() => {
      searchRoleAssignmentTargets(cleanQuery)
        .then((items) => {
          if (current !== requestVersion.current) return;
          setTargets(items);
          setState(items.length ? "results" : "empty");
        })
        .catch(() => { if (current === requestVersion.current) setState("error"); });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [query]);
  return <div>
    <label>{label}（姓名或邮箱至少 3 个字符）<input autoComplete="off" value={query} onChange={(event) => { setQuery(event.target.value); onSelect(""); }} /></label>
    {state === "loading" && <small role="status">正在搜索同机构账号…</small>}
    {state === "empty" && <small role="status">没有找到匹配账号。</small>}
    {state === "error" && <small role="alert">账号搜索失败，请修改关键词或稍后重试。</small>}
    <label>待选账号<select value={value} onChange={(event) => onSelect(event.target.value)} required><option value="">选择账号</option>{targets.map((target) => <option key={target.id} value={target.id}>{target.display_name} · {target.email}</option>)}</select></label>
    {state === "results" && <small>搜索仅提供同机构候选账号，不代表课程/班级资格；提交时服务端仍会校验资格和 Scope。</small>}
  </div>;
}

export default function AdminCourseGovernancePanel() {
  const { canWrite, viewportReady, isNarrow } = useAdminWriteGate();
  const operationKeys = useRef<AdminOperationKeyCache>(new Map());
  const coursesRequest = useRef(0);
  const classesRequest = useRef(0);
  const courseMembersRequest = useRef(0);
  const classMembersRequest = useRef(0);
  const [courses, setCourses] = useState<AdminCourse[]>([]);
  const [courseCursor, setCourseCursor] = useState<string | null>(null);
  const [courseHasMore, setCourseHasMore] = useState(false);
  const [selectedCourseId, setSelectedCourseId] = useState("");
  const selectedCourse = courses.find((course) => course.id === selectedCourseId);
  const [classes, setClasses] = useState<AdminGovernedClass[]>([]);
  const [classCursor, setClassCursor] = useState<string | null>(null);
  const [classHasMore, setClassHasMore] = useState(false);
  const [selectedClassId, setSelectedClassId] = useState("");
  const selectedClass = classes.find((item) => item.id === selectedClassId);
  const [courseMembers, setCourseMembers] = useState<AdminCourseMember[]>([]);
  const [courseMemberStatus, setCourseMemberStatus] = useState<"active" | "removed" | "all">("active");
  const [courseMemberCursor, setCourseMemberCursor] = useState<string | null>(null);
  const [courseMemberHasMore, setCourseMemberHasMore] = useState(false);
  const [classMembers, setClassMembers] = useState<AdminClassMember[]>([]);
  const [classMemberStatus, setClassMemberStatus] = useState<"active" | "removed" | "all">("active");
  const [classMemberCursor, setClassMemberCursor] = useState<string | null>(null);
  const [classMemberHasMore, setClassMemberHasMore] = useState(false);
  const [limit, setLimit] = useState(50);
  const [courseLoading, setCourseLoading] = useState(false);
  const [classesLoading, setClassesLoading] = useState(false);
  const [courseMembersLoading, setCourseMembersLoading] = useState(false);
  const [classMembersLoading, setClassMembersLoading] = useState(false);
  const [notice, setNotice] = useState("正在读取机构课程…");
  const [noticeIsError, setNoticeIsError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<PendingAction | null>(null);
  const [classCode, setClassCode] = useState("");
  const [className, setClassName] = useState("");
  const [createClassReason, setCreateClassReason] = useState("");
  const [courseMemberTarget, setCourseMemberTarget] = useState("");
  const [courseMemberRole, setCourseMemberRole] = useState<AdminCourseMember["role"]>("student");
  const [courseMemberReason, setCourseMemberReason] = useState("");
  const [courseRemovalReasons, setCourseRemovalReasons] = useState<Record<string, string>>({});
  const [classMemberTarget, setClassMemberTarget] = useState("");
  const [classMemberReason, setClassMemberReason] = useState("");
  const [classRemovalReasons, setClassRemovalReasons] = useState<Record<string, string>>({});

  const loadCourses = useCallback(async (cursor?: string, append = false) => {
    const request = ++coursesRequest.current;
    setCourseLoading(true);
    try {
      const page = await listAdminCourses({ limit, cursor });
      if (request !== coursesRequest.current) return false;
      setCourses((current) => append ? [...current, ...page.items] : page.items);
      setCourseCursor(page.nextCursor);
      setCourseHasMore(page.hasMore);
      setSelectedCourseId((current) => current || page.items[0]?.id || "");
      setNotice(""); setNoticeIsError(false);
      return true;
    } catch (error) {
      if (request === coursesRequest.current) { setNotice(explain(error)); setNoticeIsError(true); }
      return false;
    } finally { if (request === coursesRequest.current) setCourseLoading(false); }
  }, [limit]);

  const loadClasses = useCallback(async (courseId: string, cursor?: string, append = false) => {
    if (!courseId) return false;
    const request = ++classesRequest.current;
    setClassesLoading(true);
    try {
      const page = await listAdminClasses(courseId, { limit, cursor });
      if (request !== classesRequest.current) return false;
      setClasses((current) => append ? [...current, ...page.items] : page.items);
      setClassCursor(page.nextCursor); setClassHasMore(page.hasMore);
      if (!append) setSelectedClassId((current) => page.items.some((item) => item.id === current) ? current : page.items[0]?.id ?? "");
      setNotice(""); setNoticeIsError(false);
      return true;
    } catch (error) {
      if (request === classesRequest.current) { setNotice(explain(error)); setNoticeIsError(true); }
      return false;
    } finally { if (request === classesRequest.current) setClassesLoading(false); }
  }, [limit]);

  const loadCourseMembers = useCallback(async (courseId: string, cursor?: string, append = false) => {
    if (!courseId) return false;
    const request = ++courseMembersRequest.current;
    setCourseMembersLoading(true);
    try {
      const page = await listAdminCourseMembers(courseId, courseMemberStatus, { limit, cursor });
      if (request !== courseMembersRequest.current) return false;
      setCourseMembers((current) => append ? [...current, ...page.items] : page.items);
      setCourseMemberCursor(page.nextCursor); setCourseMemberHasMore(page.hasMore);
      return true;
    } catch (error) {
      if (request === courseMembersRequest.current) { setNotice(explain(error)); setNoticeIsError(true); }
      return false;
    } finally { if (request === courseMembersRequest.current) setCourseMembersLoading(false); }
  }, [courseMemberStatus, limit]);

  const loadClassMembers = useCallback(async (classId: string, cursor?: string, append = false) => {
    if (!classId) { setClassMembers([]); return false; }
    const request = ++classMembersRequest.current;
    setClassMembersLoading(true);
    try {
      const page = await listAdminClassMembers(classId, classMemberStatus, { limit, cursor });
      if (request !== classMembersRequest.current) return false;
      setClassMembers((current) => append ? [...current, ...page.items] : page.items);
      setClassMemberCursor(page.nextCursor); setClassMemberHasMore(page.hasMore);
      return true;
    } catch (error) {
      if (request === classMembersRequest.current) { setNotice(explain(error)); setNoticeIsError(true); }
      return false;
    } finally { if (request === classMembersRequest.current) setClassMembersLoading(false); }
  }, [classMemberStatus, limit]);

  useEffect(() => { void loadCourses(); }, [loadCourses]);
  useEffect(() => {
    if (selectedCourseId) {
      void loadClasses(selectedCourseId);
      void loadCourseMembers(selectedCourseId);
    } else { setClasses([]); setCourseMembers([]); }
  }, [selectedCourseId, loadClasses, loadCourseMembers]);
  useEffect(() => { void loadClassMembers(selectedClassId); }, [selectedClassId, loadClassMembers]);
  useEffect(() => { if (!canWrite) setPending(null); }, [canWrite]);

  function requestCreateClass(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = createClassReason.trim();
    if (!canWrite || !selectedCourseId || !classCode.trim() || !className.trim() || reason.length < 8) return;
    const input = { code: classCode.trim(), name: className.trim(), reason };
    setPending({ kind: "create-class", courseId: selectedCourseId, input, summary: `将在课程「${selectedCourse?.title ?? selectedCourseId}」下创建班级「${input.code} · ${input.name}」。` });
  }

  function requestAddCourseMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = courseMemberReason.trim();
    if (!canWrite || !selectedCourseId || !courseMemberTarget || reason.length < 8) return;
    const target = { user_id: courseMemberTarget, role: courseMemberRole, reason };
    setPending({ kind: "add-course-member", courseId: selectedCourseId, input: target, summary: `向课程「${selectedCourse?.title ?? selectedCourseId}」加入账号 ${courseMemberTarget}，课程角色为 ${courseMemberRole}。` });
  }

  function requestRemoveCourseMember(item: AdminCourseMember, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = courseRemovalReasons[item.id]?.trim() ?? "";
    if (!canWrite || reason.length < 8 || item.status !== "active") return;
    setPending({ kind: "remove-course-member", courseId: selectedCourseId, item, reason, summary: `软移除 ${item.display_name}（${item.role}）在课程「${selectedCourse?.title ?? selectedCourseId}」中的成员关系，当前版本 v${item.version}。` });
  }

  function requestAddClassMember(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = classMemberReason.trim();
    if (!canWrite || !selectedClassId || !classMemberTarget || reason.length < 8) return;
    setPending({ kind: "add-class-member", classId: selectedClassId, input: { user_id: classMemberTarget, reason }, summary: `将账号 ${classMemberTarget} 加入班级「${selectedClass?.code ?? ""} · ${selectedClass?.name ?? selectedClassId}」。此入口只添加已是该课程有效学生成员的账号。` });
  }

  function requestRemoveClassMember(item: AdminClassMember, event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const reason = classRemovalReasons[item.id]?.trim() ?? "";
    if (!canWrite || reason.length < 8 || item.status !== "active") return;
    setPending({ kind: "remove-class-member", classId: selectedClassId, item, reason, summary: `软移除 ${item.display_name} 在班级「${selectedClass?.code ?? ""} · ${selectedClass?.name ?? selectedClassId}」中的成员关系，当前版本 v${item.version}。` });
  }

  async function refreshPending(action: PendingAction) {
    if (action.kind === "create-class") await loadClasses(action.courseId);
    else if (action.kind === "add-course-member" || action.kind === "remove-course-member") await loadCourseMembers(action.courseId);
    else await loadClassMembers(action.classId);
  }

  async function confirmPending() {
    if (!pending || !canWrite || busy) return;
    const action = pending;
    setBusy(true);
    try {
      let receipt: string;
      if (action.kind === "create-class") {
        const result = await createAdminClass(action.courseId, action.input, adminOperationKey(operationKeys.current, "create-class", action.input));
        clearAdminOperationKey(operationKeys.current, "create-class");
        setClassCode(""); setClassName(""); setCreateClassReason("");
        receipt = `班级已创建：${result.code} · ${result.name} · ${result.id} · v${result.version}。`;
      } else if (action.kind === "add-course-member") {
        const result = await addAdminCourseMember(action.courseId, action.input, adminOperationKey(operationKeys.current, "add-course-member", action.input));
        clearAdminOperationKey(operationKeys.current, "add-course-member");
        setCourseMemberTarget(""); setCourseMemberReason("");
        window.dispatchEvent(new CustomEvent("admin-course-membership-changed", { detail: { courseId: action.courseId } }));
        receipt = `课程成员已加入：${result.display_name} · ${result.role} · ${result.id} · v${result.version}。`;
      } else if (action.kind === "remove-course-member") {
        const operation = `remove-course-member:${action.item.id}`;
        const input = { version: action.item.version, reason: action.reason };
        const result = await removeAdminCourseMember(action.courseId, action.item.id, action.item.version, action.reason, adminOperationKey(operationKeys.current, operation, input));
        clearAdminOperationKey(operationKeys.current, operation);
        setCourseRemovalReasons((current) => ({ ...current, [action.item.id]: "" }));
        window.dispatchEvent(new CustomEvent("admin-course-membership-changed", { detail: { courseId: action.courseId } }));
        receipt = `课程成员关系已软移除：${result.id} · ${result.status} · v${result.version}。历史记录未物理删除。`;
      } else if (action.kind === "add-class-member") {
        const result = await addAdminClassMember(action.classId, action.input, adminOperationKey(operationKeys.current, "add-class-member", action.input));
        clearAdminOperationKey(operationKeys.current, "add-class-member");
        setClassMemberTarget(""); setClassMemberReason("");
        receipt = `班级成员已加入：${result.display_name} · ${result.id} · v${result.version}。`;
      } else {
        const operation = `remove-class-member:${action.item.id}`;
        const input = { version: action.item.version, reason: action.reason };
        const result = await removeAdminClassMember(action.classId, action.item.id, action.item.version, action.reason, adminOperationKey(operationKeys.current, operation, input));
        clearAdminOperationKey(operationKeys.current, operation);
        setClassRemovalReasons((current) => ({ ...current, [action.item.id]: "" }));
        receipt = `班级成员关系已软移除：${result.id} · ${result.status} · v${result.version}。历史记录未物理删除。`;
      }
      setPending(null);
      await refreshPending(action);
      if (action.kind === "create-class") setSelectedClassId("");
      setNotice(receipt); setNoticeIsError(false);
    } catch (error) {
      setPending(null);
      await refreshPending(action);
      setNotice(explainConflict(error)); setNoticeIsError(true);
    } finally { setBusy(false); }
  }

  const statusOptions = <><option value="active">有效</option><option value="removed">已移除</option><option value="all">全部</option></>;

  return <section className="data-panel">
    <div className="panel-heading"><div><h2>课程、班级与成员治理</h2><p>管理同机构课程下的班级元数据、课程成员与班级学生成员；删除均为带版本和理由的软移除。</p></div>
      <div className="admin-job-panel-actions"><label>每页<select value={limit} onChange={(event) => setLimit(Number(event.target.value))}><option value={25}>25</option><option value={50}>50</option><option value={100}>100</option><option value={200}>200</option></select></label><button className="secondary-button" type="button" disabled={courseLoading} onClick={() => void loadCourses()}>刷新课程</button></div>
    </div>
    {notice && <p className="status-banner" role={noticeIsError ? "alert" : "status"}>{notice}</p>}
    {viewportReady && isNarrow && <p className="status-banner" role="status">窄屏只读：创建班级、增删课程/班级成员请使用宽屏；当前仍可查看课程和名单。</p>}
    {courseLoading && <p className="status-banner" role="status">正在读取机构课程…</p>}
    {!courseLoading && !courses.length && !notice && <p className="empty-state">当前机构没有可管理课程。</p>}
    {courses.length > 0 && <p className="empty-state">已加载 {courses.length} 门课程{courseHasMore ? "，还有更多课程" : "，当前已到末尾"}。</p>}
    {courses.length > 0 && <label>课程<select value={selectedCourseId} onChange={(event) => { setSelectedCourseId(event.target.value); setSelectedClassId(""); }}>{courses.map((course) => <option key={course.id} value={course.id}>{course.title} · {course.term} · {course.status} · v{course.version}</option>)}</select></label>}
    {courseHasMore && courseCursor && <button className="secondary-button" type="button" disabled={courseLoading} onClick={() => void loadCourses(courseCursor, true)}>加载更多课程</button>}
    {selectedCourse && <>
      <h3>班级目录 · {selectedCourse.title}</h3>
      <p className="empty-state">已加载 {classes.length} 个班级{classHasMore ? "，还有更多班级" : "，当前已到末尾"}。</p>
      {classesLoading && <p className="status-banner" role="status">正在读取班级目录…</p>}
      {classes.map((item) => <article className="question-card" key={item.id}>
        <div><strong>{item.code} · {item.name}</strong><small>{item.status} · v{item.version} · 学生/成员 {item.member_count} · 有效任课教师 {item.active_teacher_count}</small><small>更新：{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
        <button className="secondary-button" type="button" aria-pressed={item.id === selectedClassId} onClick={() => setSelectedClassId(item.id)}>{item.id === selectedClassId ? "当前班级" : "管理班级成员"}</button>
      </article>)}
      {!classesLoading && !classes.length && !notice && <p className="empty-state">该课程暂无班级。</p>}
      {classHasMore && classCursor && <button className="secondary-button" type="button" disabled={classesLoading} onClick={() => void loadClasses(selectedCourseId, classCursor, true)}>加载更多班级</button>}
      {canWrite && <form className="stack-form" onSubmit={requestCreateClass}><h3>创建班级</h3>
        <label>班级代码<input value={classCode} onChange={(event) => setClassCode(event.target.value)} maxLength={80} required /></label>
        <label>班级名称<input value={className} onChange={(event) => setClassName(event.target.value)} maxLength={200} required /></label>
        <label>创建理由（至少 8 个字符）<textarea value={createClassReason} onChange={(event) => setCreateClassReason(event.target.value)} minLength={8} maxLength={500} required /></label>
        <button className="primary-button" type="submit" disabled={busy || !classCode.trim() || !className.trim() || createClassReason.trim().length < 8}>复核并创建班级</button>
      </form>}
      <div className="panel-heading"><h3>课程成员 · {selectedCourse.title}</h3><label>成员状态<select value={courseMemberStatus} onChange={(event) => setCourseMemberStatus(event.target.value as typeof courseMemberStatus)}>{statusOptions}</select></label></div>
      <p className="empty-state">已加载 {courseMembers.length} 名课程成员{courseMemberHasMore ? "，还有更多成员" : "，当前已到末尾"}。</p>
      {courseMembersLoading && <p className="status-banner" role="status">正在读取课程成员…</p>}
      {courseMembers.map((item) => <article className="question-card" key={item.id}><div><strong>{item.display_name} · {item.role}</strong><small>用户 {item.user_id} · {item.status} · v{item.version}</small><small>更新：{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
        {canWrite && item.status === "active" && <details><summary>软移除课程成员</summary><form className="stack-form" onSubmit={(event) => requestRemoveCourseMember(item, event)}><label>移除理由（至少 8 个字符）<textarea value={courseRemovalReasons[item.id] ?? ""} onChange={(event) => setCourseRemovalReasons((current) => ({ ...current, [item.id]: event.target.value }))} minLength={8} maxLength={500} required /></label><button className="secondary-button" type="submit" disabled={busy || (courseRemovalReasons[item.id]?.trim().length ?? 0) < 8}>复核后移除</button></form></details>}
      </article>)}
      {!courseMembersLoading && !courseMembers.length && !notice && <p className="empty-state">当前课程状态筛选下没有成员。</p>}
      {courseMemberHasMore && courseMemberCursor && <button className="secondary-button" type="button" disabled={courseMembersLoading} onClick={() => void loadCourseMembers(selectedCourseId, courseMemberCursor, true)}>加载更多课程成员</button>}
      {canWrite && <form className="stack-form" onSubmit={requestAddCourseMember}><h3>加入课程成员</h3>
        <TargetPicker label="搜索同机构候选账号" value={courseMemberTarget} onSelect={setCourseMemberTarget} />
        <label>课程角色<select value={courseMemberRole} onChange={(event) => setCourseMemberRole(event.target.value as typeof courseMemberRole)}><option value="student">学生</option><option value="teacher">教师</option><option value="assistant">助教</option></select></label>
        <label>加入理由（至少 8 个字符）<textarea value={courseMemberReason} onChange={(event) => setCourseMemberReason(event.target.value)} minLength={8} maxLength={500} required /></label>
        <button className="primary-button" type="submit" disabled={busy || !courseMemberTarget || courseMemberReason.trim().length < 8}>复核并加入课程</button>
      </form>}
    </>}
    {selectedClass && <section className="data-panel" aria-label="班级成员治理">
      <div className="panel-heading"><div><h3>班级成员 · {selectedClass.code} · {selectedClass.name}</h3><p>班级成员入口只允许加入同机构且已是本课程有效学生成员的账号；服务端会再次校验。</p></div><label>成员状态<select value={classMemberStatus} onChange={(event) => setClassMemberStatus(event.target.value as typeof classMemberStatus)}>{statusOptions}</select></label></div>
      <p className="empty-state">已加载 {classMembers.length} 名班级成员{classMemberHasMore ? "，还有更多成员" : "，当前已到末尾"}。</p>
      {classMembersLoading && <p className="status-banner" role="status">正在读取班级成员…</p>}
      {classMembers.map((item) => <article className="question-card" key={item.id}><div><strong>{item.display_name}</strong><small>用户 {item.user_id} · {item.status} · v{item.version}</small><small>更新：{new Date(item.updated_at).toLocaleString("zh-CN")}</small></div>
        {canWrite && item.status === "active" && <details><summary>软移除班级成员</summary><form className="stack-form" onSubmit={(event) => requestRemoveClassMember(item, event)}><label>移除理由（至少 8 个字符）<textarea value={classRemovalReasons[item.id] ?? ""} onChange={(event) => setClassRemovalReasons((current) => ({ ...current, [item.id]: event.target.value }))} minLength={8} maxLength={500} required /></label><button className="secondary-button" type="submit" disabled={busy || (classRemovalReasons[item.id]?.trim().length ?? 0) < 8}>复核后移除</button></form></details>}
      </article>)}
      {!classMembersLoading && !classMembers.length && !notice && <p className="empty-state">当前班级状态筛选下没有成员。</p>}
      {classMemberHasMore && classMemberCursor && <button className="secondary-button" type="button" disabled={classMembersLoading} onClick={() => void loadClassMembers(selectedClassId, classMemberCursor, true)}>加载更多班级成员</button>}
      {canWrite && <form className="stack-form" onSubmit={requestAddClassMember}><h3>加入班级学生</h3>
        <TargetPicker label="搜索同机构候选账号" value={classMemberTarget} onSelect={setClassMemberTarget} />
        <label>加入理由（至少 8 个字符）<textarea value={classMemberReason} onChange={(event) => setClassMemberReason(event.target.value)} minLength={8} maxLength={500} required /></label>
        <button className="primary-button" type="submit" disabled={busy || !classMemberTarget || classMemberReason.trim().length < 8}>复核并加入班级</button>
      </form>}
    </section>}
    {!viewportReady && <p className="status-banner" role="status">正在确认屏幕尺寸；写操作暂不可用。</p>}
    <AdminConfirmationDialog
      open={Boolean(pending)}
      title={pending?.kind === "create-class" ? "复核创建班级" : pending?.kind.startsWith("add-") ? "复核加入成员" : "复核软移除成员"}
      summary={pending?.summary ?? ""}
      impact="操作仅作用于当前机构、课程或班级 Scope；移除使用版本校验并保留历史记录。搜索候选不代表资格，最终资格由服务端验证。"
      reason={pending?.kind === "remove-course-member" || pending?.kind === "remove-class-member" ? pending.reason : pending?.input.reason ?? ""}
      confirmLabel={pending?.kind === "create-class" ? "确认创建" : pending?.kind.startsWith("add-") ? "确认加入" : "确认软移除"}
      busy={busy}
      onConfirm={() => void confirmPending()}
      onCancel={() => setPending(null)}
    />
  </section>;
}
