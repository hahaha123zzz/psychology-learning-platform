"use client";

import { useEffect, useRef } from "react";

export type AdminConfirmationDialogProps = {
  open: boolean;
  title: string;
  summary: string;
  impact: string;
  reason: string;
  confirmLabel: string;
  busy?: boolean;
  onConfirm: () => void | Promise<void>;
  onCancel: () => void;
};

export default function AdminConfirmationDialog({
  open,
  title,
  summary,
  impact,
  reason,
  confirmLabel,
  busy = false,
  onConfirm,
  onCancel,
}: AdminConfirmationDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  if (!open) return null;

  return <dialog
    ref={dialogRef}
    aria-labelledby="admin-confirmation-title"
    aria-describedby="admin-confirmation-summary admin-confirmation-impact admin-confirmation-reason"
    onCancel={(event) => { event.preventDefault(); if (!busy) onCancel(); }}
    style={{
      width: "min(560px, calc(100vw - 32px))",
      maxWidth: "calc(100vw - 32px)",
      maxHeight: "calc(100vh - 32px)",
      overflow: "auto",
      border: "1px solid #cbd9df",
      borderRadius: "10px",
      padding: "22px",
      color: "#243d49",
      boxShadow: "0 18px 60px #183b4a35",
    }}
  >
    <h2 id="admin-confirmation-title">{title}</h2>
    <p id="admin-confirmation-summary">{summary}</p>
    <p id="admin-confirmation-impact"><strong>影响范围：</strong>{impact}</p>
    <p id="admin-confirmation-reason"><strong>操作理由：</strong>{reason}</p>
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "flex-end", gap: "8px", marginTop: "20px" }}>
      <button className="secondary-button" type="button" onClick={onCancel} disabled={busy}>返回修改</button>
      <button className="primary-button" type="button" onClick={() => void onConfirm()} disabled={busy}>
        {busy ? "正在处理…" : confirmLabel}
      </button>
    </div>
  </dialog>;
}
