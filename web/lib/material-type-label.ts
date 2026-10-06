const MATERIAL_TYPE_LABELS: Record<string, string> = {
  textbook: "教材",
  slides: "课件",
  handout: "讲义",
  exercise: "练习资料",
  reference: "参考资料",
  other: "课程资料",
};

/** 仅消费服务端类型；未知或旧版响应统一使用中性名称。 */
export function materialTypeLabel(value: unknown): string {
  return typeof value === "string" ? MATERIAL_TYPE_LABELS[value] ?? "课程资料" : "课程资料";
}
