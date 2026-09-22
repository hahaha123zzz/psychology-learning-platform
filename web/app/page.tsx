import Link from "next/link";
import { Icon } from "@iconify/react";

export default function Home() {
  return (
    <main className="home-app">
      <header className="home-header"><span className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</span><span>以教材为依据 · 让学习过程可追溯</span></header>
      <section className="home-hero">
        <p className="eyebrow">EXPERIMENTAL PSYCHOLOGY</p>
        <h1>从可信教材出发，<br />完成每一次有效学习。</h1>
        <p>教师审核、发布并维护教材证据；学生在原文、AI 讲解、练习和复习之间持续前进。</p>
        <div className="workspace-choices">
          <Link href="/teacher" className="workspace-choice teacher-choice"><span className="choice-icon"><Icon icon="solar:clipboard-check-bold-duotone" /></span><span><strong>进入教师工作台</strong><small>审核教材解析，管理课程与班级学情</small></span><Icon icon="solar:arrow-right-linear" /></Link>
          <Link href="/student" className="workspace-choice student-choice"><span className="choice-icon"><Icon icon="solar:book-bookmark-bold-duotone" /></span><span><strong>进入学生学习空间</strong><small>阅读教材，与 AI 教师进行有据对话</small></span><Icon icon="solar:arrow-right-linear" /></Link>
        </div>
      </section>
      <footer className="home-footer"><span><Icon icon="solar:verified-check-bold" />教材为准</span><span><Icon icon="solar:link-circle-linear" />引用可定位</span><span><Icon icon="solar:chart-2-linear" />学习可回看</span></footer>
    </main>
  );
}
