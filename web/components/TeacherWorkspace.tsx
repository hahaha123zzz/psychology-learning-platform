import Link from "next/link";

/**
 * 旧版教材发布工作台的兼容占位页。
 * 普通教师的教材编写入口已下线；实际内容管理需由后续专用管理员工作台承接。
 */
export default function TeacherWorkspace() {
  return (
    <main className="functional-app">
      <section className="functional-main" aria-labelledby="teacher-materials-retired-title">
        <h1 id="teacher-materials-retired-title">教材管理入口已调整</h1>
        <p role="status">
          当前不开放普通教师直接上传、解析、索引或发布教材。如需新增或调整课程教材，请联系课程内容管理员。
        </p>
        <Link href="/teacher/courses">返回教师课程</Link>
      </section>
    </main>
  );
}
