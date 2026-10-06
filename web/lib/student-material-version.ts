export type StudentMaterialVersion = {
  id: string;
  version_no?: number;
  status?: string;
};

export type StudentMaterialVersionSource = {
  current_version: StudentMaterialVersion | null;
  learning_version?: StudentMaterialVersion | null;
};

export function studentMaterialVersion(
  material: StudentMaterialVersionSource,
): StudentMaterialVersion | null {
  return material.learning_version ?? material.current_version;
}
