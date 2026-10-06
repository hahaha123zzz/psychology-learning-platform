"use client";

import { useEffect, useRef, type ReactNode } from "react";

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
  const drawerRef = useRef<HTMLElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return;

    returnFocusRef.current = document.activeElement instanceof HTMLElement
      ? document.activeElement
      : null;
    const drawer = drawerRef.current;
    const focusable = () => drawer?.querySelectorAll<HTMLElement>(
      'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
    ) ?? [];
    focusable()[0]?.focus();

    function trapKeyboard(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;
      const items = Array.from(focusable()).filter((item) => !item.hasAttribute("hidden"));
      if (!items.length) {
        event.preventDefault();
        drawer?.focus();
        return;
      }
      const first = items[0];
      const last = items[items.length - 1];
      if (event.shiftKey && (document.activeElement === first || !drawer?.contains(document.activeElement))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !drawer?.contains(document.activeElement))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", trapKeyboard);
    return () => {
      document.removeEventListener("keydown", trapKeyboard);
      returnFocusRef.current?.focus();
      returnFocusRef.current = null;
    };
  }, [open]);

  if (!open) return null;
  const headingId = labelledBy ?? "context-drawer-title";
  return (
    <div className="ds-drawer-backdrop" role="presentation" onMouseDown={onClose}>
      <aside
        aria-labelledby={headingId}
        aria-modal="true"
        className="ds-context-drawer"
        onMouseDown={(event) => event.stopPropagation()}
        ref={drawerRef}
        role="dialog"
        tabIndex={-1}
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
