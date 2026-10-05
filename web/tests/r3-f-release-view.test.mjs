import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import ts from "typescript";

const source = fs.readFileSync(
  new URL("../app/course-design/releases/page.tsx", import.meta.url),
  "utf8",
);

function loadManifestDiff() {
  const file = ts.createSourceFile(
    "releases-page.tsx",
    source,
    ts.ScriptTarget.ES2022,
    true,
    ts.ScriptKind.TSX,
  );
  const declarations = file.statements.filter((statement) => {
    if (ts.isTypeAliasDeclaration(statement)) return statement.name.text === "ManifestChange";
    return ts.isFunctionDeclaration(statement)
      && ["isRecord", "getManifestChanges"].includes(statement.name?.text ?? "");
  });
  const compiled = ts.transpileModule(
    declarations.map((declaration) => declaration.getText(file)).join("\n") + "\nreturn getManifestChanges;",
    { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.None } },
  );
  return new Function(compiled.outputText)();
}

test("manifest diff reports nested additions, removals, scalar changes and array item changes", () => {
  const diff = loadManifestDiff();
  const changes = diff(
    { schema_version: "course-release.v1", domain_pack: { objective: "A", removed: true }, materials: ["m1"] },
    { schema_version: "course-release.v1", domain_pack: { objective: "B", added: "evidence" }, materials: ["m1", "m2"] },
  );

  assert.deepEqual(
    changes.map(({ path, kind }) => [path, kind]),
    [
      ["manifest.domain_pack.added", "added"],
      ["manifest.domain_pack.objective", "changed"],
      ["manifest.domain_pack.removed", "removed"],
      ["manifest.materials[1]", "added"],
    ],
  );
  const objectiveChange = changes.find((change) => change.path === "manifest.domain_pack.objective");
  assert.equal(objectiveChange?.before, "A");
  assert.equal(objectiveChange?.after, "B");
});

test("Release page reads real course and release data and contains no write API calls", () => {
  assert.match(source, /api<Course\[]>\("\/courses"\)/);
  assert.match(source, /listCourseReleases\(id\)/);
  assert.match(source, /JSON\.stringify\(previewRelease\.manifest, null, 2\)/);
  assert.doesNotMatch(source, /createCourseRelease|updateCourseRelease|publishCourseRelease/);
  assert.doesNotMatch(source, /method:\s*["'](?:POST|PATCH|PUT|DELETE)["']/);
});

test("Release page names the comparison boundary and exposes loading, empty and error states", () => {
  assert.match(source, /内容差异仅供核对，不是发布门禁/);
  assert.match(source, /下方只比较两个版本的 manifest 字段/);
  assert.match(source, /正在读取版本/);
  assert.match(source, /当前课程暂无可查看的版本/);
  assert.match(source, /role="alert"/);
  assert.match(source, /至少需要两个真实课程版本才能比较/);
});
