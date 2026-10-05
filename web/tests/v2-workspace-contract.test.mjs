import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const read = (path) => fs.readFileSync(new URL(path, import.meta.url), "utf8");

test("V2 workspaces consume implemented API capabilities", () => {
  const teacher = read("../components/TeacherWorkspace.tsx");
  const student = read("../components/StudentWorkspace.tsx");
  const assessments = read("../components/StudentAssessments.tsx");
  const courseSupport = read("../components/StudentCourseSupportPages.tsx");
  const grading = read("../components/TeacherGradingPanel.tsx");
  const learning = read("../components/StudentLearningSession.tsx");
  const studentLearn = read("../components/StudentLearnPage.tsx");
  const teacherSupport = read("../components/TeacherCourseSupportPages.tsx");
  const teacherObservations = read("../components/TeacherObservationsPanel.tsx");
  const teachingAssets = read("../components/TeachingAssetEditor.tsx");
  const teacherInterventions = read("../components/TeacherInterventionsPanel.tsx");
  const home = read("../components/StudentHomeDashboard.tsx");
  const studentHomeRoute = read("../app/student/page.tsx");
  const guidedLearningRoute = read("../app/student/learning/page.tsx");
  const miniLabPanel = read("../components/StudentMiniLabPanel.tsx");
  const miniLabRuntime = read("../components/learning/MiniLabRuntime.tsx");
  const miniLabApi = read("../lib/mini-lab-api.ts");
  assert.match(teacher, /教材管理入口已调整/);
  assert.doesNotMatch(teacher, /uploadMaterialResumable|material-versions|parse-review-issues/);
  assert.match(student, /\/knowledge\/search/);
  assert.match(student, /streamChatTurn/);
  assert.match(assessments, /\/attempts\/\$\{attemptId\}\/submit/);
  assert.match(assessments, /answer_version/);
  assert.match(assessments, /setAnswers\(restoredAnswers\)/);
  assert.match(assessments, /\/answers\/\$\{questionId\}\/flag/);
  assert.match(assessments, /标记此题，稍后检查/);
  assert.match(assessments, /开考前确认/);
  assert.match(assessments, /检查未答\/标记题目/);
  assert.match(assessments, /确认提交测验/);
  assert.match(assessments, /保存失败/);
  assert.match(assessments, /文字作答/);
  assert.match(assessments, /queueEssaySave/);
  assert.match(courseSupport, /answer_version/);
  assert.match(courseSupport, /setAnswers\(restoredAnswers\)/);
  assert.match(courseSupport, /标记此题，稍后检查/);
  assert.match(courseSupport, /Promise\.allSettled/);
  assert.match(courseSupport, /current_attempt_id/);
  assert.match(courseSupport, /item\.type === "essay" \|\| item\.type === "short_answer"/);
  assert.match(courseSupport, /saved\.response\?\.text/);
  assert.match(teacherSupport, /formElement\.reset\(\)/);
  assert.doesNotMatch(teacherSupport, /event\.currentTarget\.reset\(\)/);
  for (const formPage of [teacherObservations, teachingAssets, teacherInterventions]) {
    assert.match(formPage, /formElement\.reset\(\)/);
    assert.doesNotMatch(formPage, /event\.currentTarget\.reset\(\)/);
  }
  assert.match(studentLearn, /items\.slice\(0, -2\)/);
  assert.match(studentLearn, /setQuestion\(content\)/);
  assert.match(studentLearn, /setNotice\(""\);\s+setSending\(true\)/);
  assert.match(studentLearn, /pendingTurn\.current/);
  assert.match(courseSupport, /createDeletionRecoveryMaterial/);
  assert.match(courseSupport, /JSON\.stringify\(challenge\)/);
  assert.match(courseSupport, /我已把回执编号和查询凭证保存到安全位置/);
  assert.match(grading, /grading-queue/);
  assert.match(grading, /teacher\/attempts\/\$\{detail\.attempt_id\}\/grading/);
  assert.match(grading, /Idempotency-Key/);
  assert.match(grading, /复核理由/);
  assert.match(learning, /\/learning-sessions/);
  assert.match(home, /\/student\/home/);
  assert.match(home, /student-learning-task/);
  assert.match(studentHomeRoute, /StudentHomeDashboard/);
  assert.match(guidedLearningRoute, /StudentLearningSession/);
  assert.match(miniLabPanel, /getActiveMiniLab\(courseId\)/);
  assert.match(miniLabPanel, /已保存阶段和答案均已保留/);
  assert.match(miniLabPanel, /saveMiniLabProgress\(current, trialData\)/);
  assert.match(miniLabRuntime, /initialTrialData/);
  assert.match(miniLabRuntime, /trialData\.length/);
  assert.match(miniLabApi, /\/student\/labs\/active\?course_id=/);
  assert.match(miniLabApi, /\/trials/);
});

test("formal assessment route has isolated multi-select and true-false answer controls", () => {
  const formal = read("../components/StudentAssessments.tsx");
  const formalRoute = read("../app/student/assessments/page.tsx");
  const practice = read("../components/StudentCourseSupportPages.tsx");
  assert.match(formalRoute, /StudentAssessments/);
  assert.doesNotMatch(formalRoute, /LegacyCourseRedirect/);
  assert.match(practice, /student\/assessments\?course_id=/);
  assert.match(formal, /item\.type === "multiple"/);
  assert.match(formal, /item\.type === "true_false"/);
  assert.match(formal, /type="checkbox"/);
  assert.match(formal, /saveTrueFalse/);
  assert.match(formal, /selected_keys: value/);
});

test("SSE turns are only accepted after the server confirms persistence", () => {
  const api = read("../lib/api.ts");
  assert.match(api, /event\.event === "done"/);
  assert.match(api, /event\.data\.saved !== true/);
  assert.match(api, /SSE_STREAM_INCOMPLETE/);
});

test("admin authorization changes collect target, scope and audited reasons", () => {
  const admin = read("../components/AdminRoleAssignmentsPanel.tsx");
  const api = read("../lib/admin-api.ts");
  assert.match(admin, /searchRoleAssignmentTargets/);
  assert.match(admin, /listRoleAssignmentCourses/);
  assert.match(admin, /授权理由/);
  assert.match(admin, /撤销理由/);
  assert.match(admin, /grantRoleAssignment/);
  assert.match(admin, /revokeRoleAssignment/);
  assert.match(api, /Idempotency-Key/);
});

test("admin job recovery hides task payload and requires a versioned reason", () => {
  const admin = read("../components/AdminJobsPanel.tsx");
  const api = read("../lib/admin-api.ts");
  assert.match(admin, /listAdminJobs/);
  assert.match(admin, /retryAdminJob/);
  assert.match(admin, /原始错误详情不在管理员面板展示/);
  assert.match(admin, /最多 5 次/);
  assert.match(api, /\/admin\/jobs\?status=/);
  assert.match(api, /\/admin\/jobs\/\$\{id\}\/retry/);
  assert.match(api, /Idempotency-Key/);
});

test("admin class assignment stays in course membership scope and is auditable", () => {
  const admin = read("../components/AdminClassAssignmentsPanel.tsx");
  const api = read("../lib/admin-api.ts");
  assert.match(admin, /getAdminClassAssignmentOptions/);
  assert.match(admin, /任课对象必须已是该课程的教师或助教成员/);
  assert.match(admin, /分配理由/);
  assert.match(admin, /结束理由/);
  assert.match(admin, /assignAdminClassTeacher/);
  assert.match(admin, /endAdminClassTeacherAssignment/);
  assert.match(api, /\/admin\/class-assignment-options\?course_id=/);
  assert.match(api, /\/admin\/class-teacher-assignments/);
  assert.match(api, /Idempotency-Key/);
});

test("Domain Pack editor explains textbook-backed ExperimentSchema fields", () => {
  const editor = read("../components/CourseDesignPackEditor.tsx");
  assert.match(editor, /pack === "domain_pack"/);
  assert.match(editor, /ExperimentSchema 字段说明/);
  assert.match(editor, /教材未提供的信息请省略或留空/);
  assert.match(editor, /research_question、hypothesis、iv、dv/);
  assert.match(editor, /controls\/confounds 使用字符串数组/);
  assert.match(editor, /textbook_evidence 填 EvidenceBinding 稳定 key 数组/);
});

test("student textbook citations reopen version-bound evidence pointers", () => {
  const studentLearn = read("../components/StudentLearnPage.tsx");
  const pointerDrawer = read("../components/learning/EvidencePointerDrawer.tsx");
  assert.match(studentLearn, /evidence_pointer_id/);
  assert.match(studentLearn, /EvidencePointerDrawer/);
  assert.match(pointerDrawer, /\/evidence-pointers\/\$\{pointerId\}/);
  assert.match(pointerDrawer, /正在重新校验权限并读取引用/);
  assert.match(pointerDrawer, /\/evidence-pointers\/\$\{pointerId\}\/page-image/);
  assert.match(pointerDrawer, /cache: "no-store"/);
  assert.match(pointerDrawer, /不伪造页图或高亮/);
});

test("privacy deletion presents recovery material before submission and clears local data", () => {
  const profile = read("../components/StudentProfile.tsx");
  assert.match(profile, /\/me\/privacy\/delete-request/);
  assert.match(profile, /completed_with_retention/);
  assert.match(profile, /retained_categories/);
  assert.match(profile, /setSummary\(null\)/);
  assert.match(profile, /setItems\(\[\]\)/);
  assert.match(profile, /deletionReceipt \? \(/);
  assert.match(profile, /正式答卷、成绩与审计按明确保留边界留存/);
  assert.match(profile, /createDeletionRecoveryMaterial/);
  assert.match(profile, /JSON\.stringify\(deletionChallenge\)/);
  assert.match(profile, /setRecoverySaved\(event\.target\.checked\)/);
  assert.match(profile, /status_credential/);
  assert.match(profile, /privacy\/deletion-status/);
  const lookup = read("../components/PrivacyDeletionStatusLookup.tsx");
  assert.match(lookup, /api<DeletionStatus>\("\/privacy\/deletion-status"/);
  assert.match(lookup, /\/privacy\/deletion-status\/retry/);
  assert.match(lookup, /无需登录/);
  const generator = read("../lib/privacy-deletion.ts");
  assert.match(generator, /crypto\.getRandomValues/);
  assert.match(generator, /newUlid/);
});

test("V2 proxy keeps the browser on the cookie origin", () => {
  const config = read("../next.config.ts");
  const client = read("../lib/api.ts");
  assert.match(config, /source: "\/api\/:path\*"/);
  assert.match(client, /credentials: "include"/);
});
