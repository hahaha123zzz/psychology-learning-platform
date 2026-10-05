import HtmlButtonResponsePlugin from "@jspsych/plugin-html-button-response";

export const MINI_LAB_SCHEMA_VERSION = "mini-lab.v1";

export type MiniLabPhase = "intro" | "predict" | "run" | "inspect" | "explain" | "summary";

export type MiniLabDefinition = {
  id: string;
  title: string;
  intro: string;
  prediction: { prompt: string; choices: string[] };
  run: { prompt: string; choices: string[] };
  inspect: string;
  explanation: string;
  summary: string;
  source_status?: "engineering_fixture";
  source_note?: string;
};

export type MiniLabTrialData = {
  phase: MiniLabPhase;
  response: number | null;
  rt: number | null;
  recorded_at: string;
};

export type MiniLabResult = {
  schema_version: typeof MINI_LAB_SCHEMA_VERSION;
  definition_id: string;
  runtime: "jspsych";
  trial_data: MiniLabTrialData[];
  completed_at: string;
};

export type MiniLabTimeline = Array<Record<string, unknown>>;

function escapeHtml(value: string): string {
  return value.replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[
        character
      ] ?? character,
  );
}

function screen(title: string, body: string): string {
  return `<section class="mini-lab-screen"><p class="mini-lab-kicker">实验学习</p><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></section>`;
}

function buttonChoices(choices: string[]): string[] {
  return choices.map(escapeHtml);
}

export function buildMiniLabTimeline(
  definition: MiniLabDefinition,
  onTrial: (data: MiniLabTrialData) => void | Promise<void>,
  completedCount = 0,
): MiniLabTimeline {
  const trial = (
    phase: MiniLabPhase,
    stimulus: string,
    choices: string[],
  ): Record<string, unknown> => ({
    type: HtmlButtonResponsePlugin,
    stimulus,
    choices: buttonChoices(choices),
    css_classes: ["mini-lab-trial"],
    on_finish: async (data: { response?: number | null; rt?: number | null }) => {
      await onTrial({
        phase,
        response: typeof data.response === "number" ? data.response : null,
        rt: typeof data.rt === "number" ? data.rt : null,
        recorded_at: new Date().toISOString(),
      });
    },
  });

  return [
    trial("intro", screen(definition.title, definition.intro), ["开始"]),
    trial("predict", screen("先做预测", definition.prediction.prompt), definition.prediction.choices),
    trial("run", screen("运行实验", definition.run.prompt), definition.run.choices),
    trial("inspect", screen("观察结果", definition.inspect), ["我已观察"]),
    trial("explain", screen("解释现象", definition.explanation), ["查看总结"]),
    trial("summary", screen("带走结论", definition.summary), ["完成"]),
  ].slice(completedCount);
}

export function createMiniLabResult(
  definitionId: string,
  trialData: MiniLabTrialData[],
  completedAt = new Date().toISOString(),
): MiniLabResult {
  return {
    schema_version: MINI_LAB_SCHEMA_VERSION,
    definition_id: definitionId,
    runtime: "jspsych",
    trial_data: trialData.map((item) => ({ ...item })),
    completed_at: completedAt,
  };
}
