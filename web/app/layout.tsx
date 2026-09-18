import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "实验心理学智能学习平台",
  description: "教材有据、教师可控、过程可追的智能学习平台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>
        <div className="shell">
          <header className="topbar">
            <Link className="brand" href="/">实验心理学智能学习平台</Link>
            <nav className="nav" aria-label="工作区导航">
              <Link href="/student">学生空间</Link>
              <Link href="/teacher">教师空间</Link>
              <Link href="/admin">管理空间</Link>
            </nav>
          </header>
          {children}
        </div>
      </body>
    </html>
  );
}

