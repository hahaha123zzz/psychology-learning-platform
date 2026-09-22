"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Icon } from "@iconify/react";
import { api, ApiError } from "../../lib/api";

type Me = { display_name: string; platform_roles: string[] };

export default function LoginPage() {
  const router = useRouter(); const search = useSearchParams();
  const [email, setEmail] = useState("teacher@demo.edu"); const [password, setPassword] = useState("demo-password-123");
  const [error, setError] = useState(""); const [loading, setLoading] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setLoading(true); setError("");
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) });
      const me = await api<Me>("/me");
      const requested = search.get("next");
      const target = requested === "/teacher" || requested === "/student" ? requested : (me.platform_roles.includes("teacher") ? "/teacher" : "/student");
      router.replace(target);
    } catch (reason) { setError(reason instanceof ApiError ? reason.message : "无法连接服务，请确认本地服务已启动。"); }
    finally { setLoading(false); }
  }
  return <main className="login-page"><section className="login-card"><Link href="/" className="app-brand"><Icon icon="solar:book-2-bold-duotone" />实验心理学智能学习平台</Link><h1>登录学习空间</h1><p>使用已开通的教学账号继续。</p><form onSubmit={submit}><label>邮箱<input type="email" value={email} onChange={e => setEmail(e.target.value)} required /></label><label>密码<input type="password" value={password} onChange={e => setPassword(e.target.value)} required /></label>{error && <p className="form-error">{error}</p>}<button className="primary-button" disabled={loading}>{loading ? "正在登录…" : "登录"}</button></form><small>演示教师：teacher@demo.edu；演示学生：student@demo.edu</small></section></main>;
}
