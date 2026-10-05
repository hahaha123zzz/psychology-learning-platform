"use client";

import { useEffect, useRef, useState } from "react";
import {
  buildMiniLabTimeline,
  createMiniLabResult,
  type MiniLabDefinition,
  type MiniLabResult,
  type MiniLabTrialData,
} from "../../lib/mini-lab/jspsych-adapter";

export default function MiniLabRuntime({
  definition,
  initialTrialData,
  onTrial,
  onComplete,
  onRecover,
}: {
  definition: MiniLabDefinition;
  initialTrialData: MiniLabTrialData[];
  onTrial: (trialData: MiniLabTrialData[]) => Promise<void>;
  onComplete?: (result: MiniLabResult) => void | Promise<void>;
  onRecover: () => Promise<void>;
}) {
  const displayRef = useRef<HTMLDivElement>(null);
  const definitionRef = useRef(definition);
  const initialTrialDataRef = useRef(initialTrialData);
  const onTrialRef = useRef(onTrial);
  const onCompleteRef = useRef(onComplete);
  const [status, setStatus] = useState<"loading" | "ready" | "complete" | "error">("loading");

  useEffect(() => {
    definitionRef.current = definition;
    initialTrialDataRef.current = initialTrialData;
    onTrialRef.current = onTrial;
    onCompleteRef.current = onComplete;
  }, [definition, initialTrialData, onTrial, onComplete]);

  useEffect(() => {
    let disposed = false;
    const trialData: MiniLabTrialData[] = initialTrialDataRef.current.map((trial) => ({ ...trial }));

    async function run() {
      if (!displayRef.current) return;
      try {
        const currentDefinition = definitionRef.current;
        if (trialData.length === 6) {
          setStatus("complete");
          await onCompleteRef.current?.(createMiniLabResult(currentDefinition.id, trialData));
          return;
        }
        const [{ initJsPsych }, { default: HtmlButtonResponsePlugin }] = await Promise.all([
          import("jspsych"),
          import("@jspsych/plugin-html-button-response"),
        ]);
        if (disposed || !displayRef.current) return;
        const timeline = buildMiniLabTimeline(
          currentDefinition,
          async (data) => {
            trialData.push(data);
            await onTrialRef.current(trialData.map((trial) => ({ ...trial })));
          },
          trialData.length,
        );
        // 明确动态注册官方插件，避免 Next.js 服务端渲染阶段触碰浏览器运行时。
        void HtmlButtonResponsePlugin;
        const jsPsych = initJsPsych({ display_element: displayRef.current });
        setStatus("ready");
        await jsPsych.run(timeline as Parameters<typeof jsPsych.run>[0]);
        if (!disposed) {
          setStatus("complete");
          await onCompleteRef.current?.(createMiniLabResult(currentDefinition.id, trialData));
        }
      } catch {
        if (!disposed) setStatus("error");
      }
    }

    void run();
    return () => {
      disposed = true;
    };
  // Session snapshots/callbacks change after each persisted trial; only a new lab starts a runtime.
  }, [definition.id]);

  return (
    <section className="mini-lab-runtime" aria-label={`${definition.title}实验`}>
      {status === "loading" && <p className="mini-lab-status">正在准备实验运行时…</p>}
      {status === "error" && <div className="mini-lab-status error" role="alert">
        <p>实验或保存过程已中断。未确认保存的试次不会作为完成记录；可以重新读取服务端已保存阶段。</p>
        <button className="secondary-button" type="button" onClick={() => void onRecover()}>恢复已保存阶段</button>
      </div>}
      <div ref={displayRef} className="mini-lab-display" data-status={status} />
      {status === "complete" && <p className="mini-lab-status">实验记录已生成，等待学习证据校验。</p>}
    </section>
  );
}
