import type { Metadata } from "next";
import "../design-system/tokens.css";
import "../design-system/learning-blocks.css";
import "../design-system/mini-lab.css";
import "./globals.css";

export const metadata: Metadata = {
  title: "实验心理学智能学习平台",
  description: "教材有据、教师可控、过程可追的智能学习平台",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
