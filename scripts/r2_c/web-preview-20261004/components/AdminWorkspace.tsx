"use client";

import { useState } from "react";
import Link from "next/link";
import { Icon } from "@iconify/react";
import AdminClassAssignmentsPanel from "./AdminClassAssignmentsPanel";
import AdminJobsPanel from "./AdminJobsPanel";
import AdminRoleAssignmentsPanel from "./AdminRoleAssignmentsPanel";
import AdminAuditPanel from "./AdminAuditPanel";
import AdminOverviewPanel from "./AdminOverviewPanel";

const sections = [
  { id: "overview", title: "运行概览", description: "基础服务状态" },
  { id: "iam", title: "IAM 授权", description: "平台与课程角色" },
  { id: "classes", title: "课程与班级", description: "班级任课 Scope" },
  { id: "jobs", title: "任务恢复", description: "教材解析与索引" },
  { id: "audit", title: "审计日志", description: "治理操作记录" },
] as const;

type AdminSection = (typeof sections)[number]["id"];

export default function AdminWorkspace() {
  const [activeSection, setActiveSection] = useState<AdminSection>("overview");

  return <main className="functional-app">
    <header className="app-header">
      <Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link>
      <strong>管理员治理工作台</strong>
      <div className="header-spacer" />
    </header>
    <section className="functional-layout">
      <nav className="functional-nav" role="tablist" aria-label="管理员治理导航" aria-orientation="vertical">
        <strong>治理导航</strong>
        {sections.map((section) => <button
          key={section.id}
          id={`admin-tab-${section.id}`}
          className={`data-nav${activeSection === section.id ? " active" : ""}`}
          type="button"
          role="tab"
          aria-selected={activeSection === section.id}
          aria-controls={`admin-panel-${section.id}`}
          tabIndex={activeSection === section.id ? 0 : -1}
          onClick={() => setActiveSection(section.id)}
          onKeyDown={(event) => {
            const currentIndex = sections.findIndex((item) => item.id === section.id);
            const nextIndex = event.key === "ArrowDown"
              ? (currentIndex + 1) % sections.length
              : event.key === "ArrowUp"
                ? (currentIndex + sections.length - 1) % sections.length
                : event.key === "Home"
                  ? 0
                  : event.key === "End"
                    ? sections.length - 1
                    : currentIndex;
            if (nextIndex === currentIndex) return;
            event.preventDefault();
            const nextSection = sections[nextIndex];
            setActiveSection(nextSection.id);
            window.requestAnimationFrame(() => document.getElementById(`admin-tab-${nextSection.id}`)?.focus());
          }}
        >
          {section.title}<small>{section.description}</small>
        </button>)}
        <h3>权限边界</h3>
        <p className="empty-state">管理员治理操作仍受机构、课程和班级 Scope 约束；此工作台不授予教材正文或学生私聊读取权。</p>
      </nav>
      <section className="functional-main" aria-label="管理员工作区内容">
        <div id="admin-panel-overview" role="tabpanel" aria-labelledby="admin-tab-overview" hidden={activeSection !== "overview"}>
          <AdminOverviewPanel />
        </div>
        <div id="admin-panel-iam" role="tabpanel" aria-labelledby="admin-tab-iam" hidden={activeSection !== "iam"}>
          <AdminRoleAssignmentsPanel />
        </div>
        <div id="admin-panel-classes" role="tabpanel" aria-labelledby="admin-tab-classes" hidden={activeSection !== "classes"}>
          <AdminClassAssignmentsPanel />
        </div>
        <div id="admin-panel-jobs" role="tabpanel" aria-labelledby="admin-tab-jobs" hidden={activeSection !== "jobs"}>
          <AdminJobsPanel />
        </div>
        <div id="admin-panel-audit" role="tabpanel" aria-labelledby="admin-tab-audit" hidden={activeSection !== "audit"}>
          <AdminAuditPanel />
        </div>
      </section>
    </section>
  </main>;
}
