"use client";

import { useEffect, useState } from "react";

export function useAdminWriteGate() {
  const [viewportReady, setViewportReady] = useState(false);
  const [wideEnough, setWideEnough] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(min-width: 721px)");
    const update = () => {
      setWideEnough(media.matches);
      setViewportReady(true);
    };
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  return {
    canWrite: viewportReady && wideEnough,
    viewportReady,
    isNarrow: viewportReady && !wideEnough,
  };
}
