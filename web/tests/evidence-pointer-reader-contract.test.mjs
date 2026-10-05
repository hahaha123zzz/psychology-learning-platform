import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/learning/EvidencePointerDrawer.tsx", import.meta.url),
  "utf8",
);

test("Reader requests each persisted physical-page anchor and rejects mismatched page images", () => {
  assert.match(source, /anchors\?: EvidenceAnchor\[\]\s*\|\s*null/);
  assert.match(source, /anchorsFor\(result\)/);
  assert.match(source, /new URLSearchParams\(\{ physical_page: String\(selectedPhysicalPage\) \}\)/);
  assert.match(source, /X-Reader-Physical-Page/);
  assert.match(source, /physicalPage !== selectedPhysicalPage/);
});

test("Reader controls are keyboard-operable and rotate the image and bbox in one layer", () => {
  assert.match(source, /<label[^>]*>引用定位页<\/label>/);
  assert.match(source, /<select[\s\S]*?anchors\.map/);
  assert.match(source, /aria-label="缩小页图"/);
  assert.match(source, /aria-label="放大页图"/);
  assert.match(source, /aria-label="顺时针旋转页图"/);
  assert.match(source, /transform: `translate\(-50%, -50%\) rotate\(\$\{rotation\}deg\)`/);
  assert.match(source, /position: "absolute"[\s\S]*?bboxPixels/);
  assert.match(source, /该来源没有可验证的物理页和 PDF 页内坐标/);
});
