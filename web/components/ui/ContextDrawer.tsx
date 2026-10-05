"use client";

import type { ReactNode } from "react";

export function ContextDrawer({
  open,
  title,
  children,
  onClose,
  labelledBy,
}: {
  open: boolean;
  title: string;
  children: ReactNode;
  onClose: () => void;
  labelledBy?: string;
}) {
  if (!open) return null;
  const headingId = labelledBy ?? "context-drawer-title";
  return (
    <div className="ds-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-labelledby={headingId}
        aria-modal="true"
        className="ds-context-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        role="dialog"
      >
        <header className="ds-drawer-header">
          <h2 id={headingId}>{title}</h2>
          <button aria-label="关闭上下文面板" className="ds-icon-button" onClick={onClose} type="button">×</button>
        </header>
        <div className="ds-drawer-body">{children}</div>
      </aside>
    </div>
  );
}
