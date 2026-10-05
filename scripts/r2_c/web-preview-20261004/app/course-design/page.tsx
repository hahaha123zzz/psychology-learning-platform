import Link from "next/link";

export default function CourseDesignOverviewPage() {
  return <main className="functional-app" style={{ padding: "32px" }}><p className="eyebrow">COURSE DESIGNER</p><h1>课程设计</h1><p>从当前课程的发布草稿编辑领域、教学和测评 Pack；保存和发布均由服务端版本门禁控制。</p><div className="practice-grid"><Link className="data-panel" href="/course-design/domain"><h2>领域知识</h2><p>编辑 Domain Pack</p></Link><Link className="data-panel" href="/course-design/pedagogy"><h2>教学设计</h2><p>编辑 Pedagogy Pack</p></Link><Link className="data-panel" href="/course-design/assessment"><h2>测评设计</h2><p>编辑 Assessment Pack</p></Link><Link className="data-panel" href="/course-design/releases"><h2>发布</h2><p>创建、检查和发布课程版本</p></Link></div></main>;
}
