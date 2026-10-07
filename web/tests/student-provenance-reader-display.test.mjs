import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
import {
  readStudentProvenance,
  studentCourseResourceRoleLabel,
  studentProvenanceStatusLabel,
} from "../lib/student-provenance.ts";

const reader = await readFile(new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url), "utf8");
const learn = await readFile(new URL("../components/StudentLearnPage.tsx", import.meta.url), "utf8");
const display = await readFile(new URL("../components/learning/StudentProvenanceMetadata.tsx", import.meta.url), "utf8");
const projection = await readFile(new URL("../lib/student-provenance.ts", import.meta.url), "utf8");

const syntheticProvenance = (overrides = {}) => ({
  source_title: "合成来源",
  publisher: "合成发布方",
  content_author: "合成作者",
  edition: "第 2 版",
  source_url: "https://example.invalid/source",
  license: "Synthetic license",
  course_resource_role: "course_textbook",
  status: "unreviewed",
  version: 3,
  submitted_by: "private-submitter",
  reviewed_by: "private-reviewer",
  review_note: "private audit note",
  ...overrides,
});

test("normalizes only the server-safe provenance allowlist and drops reviewer-private fields", () => {
  const provenance = readStudentProvenance(syntheticProvenance());
  assert.deepEqual(provenance, {
    source_title: "合成来源",
    publisher: "合成发布方",
    content_author: "合成作者",
    edition: "第 2 版",
    source_url: "https://example.invalid/source",
    license: "Synthetic license",
    course_resource_role: "course_textbook",
    status: "unreviewed",
    version: 3,
  });
  assert.doesNotMatch(JSON.stringify(provenance), /private-submitter|private-reviewer|private audit note/);
  assert.doesNotMatch(projection, /submitted_by|reviewed_by|review_note/);
});

test("verified, unreviewed, rejected, and null states remain explicit and non-authoritative", () => {
  assert.equal(studentProvenanceStatusLabel(readStudentProvenance(syntheticProvenance({ status: "verified" }))?.status ?? null), "课程已审核来源信息");
  assert.equal(studentProvenanceStatusLabel(readStudentProvenance(syntheticProvenance())?.status ?? null), "来源信息待课程审核");
  assert.equal(studentProvenanceStatusLabel(readStudentProvenance(syntheticProvenance({ status: "rejected" }))?.status ?? null), "课程审核未通过");
  assert.equal(readStudentProvenance(null), null);
  assert.equal(readStudentProvenance(undefined), null);
  assert.equal(readStudentProvenance({ status: "legacy", version: 1 }), null);
  assert.equal(studentProvenanceStatusLabel(null), "来源信息未提供");
  assert.match(projection, /return "课程已审核来源信息"/);
  assert.match(projection, /return "来源信息待课程审核"/);
  assert.match(projection, /return "课程审核未通过"/);
  assert.doesNotMatch(display, /外部核验|权威认证|权威来源/);
});

test("course resource role labels are server-derived and null remains unclassified", () => {
  assert.equal(studentCourseResourceRoleLabel("course_textbook"), "课程教材用途");
  assert.equal(studentCourseResourceRoleLabel("supplementary_resource"), "补充课程资料");
  assert.equal(studentCourseResourceRoleLabel(null), "课程用途未分类");
  assert.match(display, /课程用途未分类/);
  assert.match(display, /studentCourseResourceRoleLabel\(provenance\.course_resource_role\)/);
  assert.doesNotMatch(projection, /material_type|material_title|title.*course_resource_role/);
});

test("Reader and Tutor citations use only their authorized server provenance fields", () => {
  assert.match(reader, /provenance\?: unknown/);
  assert.match(reader, /readStudentProvenance\(view\.provenance\)/);
  assert.match(learn, /provenance\?: unknown/);
  assert.match(learn, /readStudentProvenance\(citation\.provenance\)/);
  assert.match(learn, /readStudentProvenance\(eventData\.data\.provenance\)/);
  assert.match(learn, /StudentProvenanceMetadata provenance=\{citation\.provenance\}/);
  assert.match(reader, /<StudentProvenanceMetadata provenance=\{readStudentProvenance\(view\.provenance\)\} \/>/);
  assert.match(learn, /citation\.provenance/);
  assert.match(reader, /view\.provenance/);
});

test("source_url is rendered as escaped text, never as a navigation target", () => {
  const hostileUrl = 'javascript:alert(1)"<img src=x onerror=alert(2)>';
  const provenance = readStudentProvenance(syntheticProvenance({ source_url: hostileUrl }));
  assert.equal(provenance?.source_url, hostileUrl);
  assert.match(display, /<dd>\{valueOrUnavailable\(provenance\.source_url\)\}<\/dd>/);
  assert.doesNotMatch(display, /href=\{[^}]*source_url|window\.location|location\.href/);
});
