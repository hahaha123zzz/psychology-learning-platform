import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";

const source = fs.readFileSync(
  new URL("../components/StudentLearnPage.tsx", import.meta.url),
  "utf8",
);
const restoreEffect = source.slice(source.indexOf("useEffect(() => {", source.indexOf("sessionRestoreRequested")), source.indexOf("async function search"));

test("Learn restores only an explicit owned session matching the current course", () => {
  assert.match(source, /useSearchParams/);
  assert.match(source, /const restoreRequested = searchParams\.has\("session_id"\)/);
  assert.match(restoreEffect, /if \(!restoreRequested\)/);
  assert.match(source, /const requestedSessionId = requestedSessionParam\?\.trim\(\) \?\? ""/);
  assert.match(restoreEffect, /api<SavedChatSession>\(`\/chat\/sessions\/\$\{encodeURIComponent\(requestedSessionId\)\}`\)/);
  assert.match(restoreEffect, /saved\.id !== requestedSessionId \|\| saved\.course_id !== courseId/);
  assert.match(restoreEffect, /saved\.mode !== "course_qa"/);
  assert.match(restoreEffect, /loadedSessionRef\.current\?\.id === requestedSessionId && loadedSessionRef\.current\.courseId === courseId/);
  assert.doesNotMatch(restoreEffect, /method:\s*"POST"|\/knowledge\/search/);
});

test("Learn restores saved student and tutor turns and maps saved evidence pointers", () => {
  assert.match(restoreEffect, /turn\.role !== "student" && turn\.role !== "tutor"/);
  assert.match(restoreEffect, /content: turn\.content/);
  assert.match(restoreEffect, /citation\.evidence_pointer_id/);
  assert.match(restoreEffect, /citation\.label/);
  assert.match(restoreEffect, /if \(!item \|\| typeof item !== "object"\) return \[\]/);
  assert.match(source, /EvidencePointerDrawer label="打开引用" pointerId=\{citation\.pointerId\}/);
});

test("Learn fails closed on invalid session restore and does not auto-create a replacement", () => {
  assert.match(restoreEffect, /setTurns\(\[\]\)/);
  assert.match(restoreEffect, /setSessionId\(""\)/);
  assert.match(restoreEffect, /setRestoreError\(\{ id: requestedSessionId, courseId,/);
  assert.match(source, /const restoreBlocked = sessionLoading \|\| Boolean\(restoreErrorForRoute\)/);
  assert.match(source, /const visibleTurns = sessionId && \(loadedSession\?\.id !== sessionId \|\| loadedSession\.courseId !== courseId\)\s*\? \[\]\s*:\s*restoreRequested && !sessionMatchesRoute \? \[\] : turns/);
  assert.match(source, /const activeSessionForRoute = restoreRequested\s*\? \(sessionMatchesRoute \? sessionId : ""\)\s*: loadedSession\?\.id === sessionId && loadedSession\.courseId === courseId\s*\? sessionId\s*: ""/);
  assert.match(source, /disabled=\{!materials\.length \|\| sending \|\| restoreBlocked(?: \|\| loadingTablePointer)?\}/);
  const send = source.slice(source.indexOf("async function send"), source.indexOf("return <div className=\"student-learn-page\""));
  assert.match(send, /if \(!activeSession\)\s*\{\s*const created = await api<\{ id: string \}>\("\/chat\/sessions"/);
  assert.match(send, /let activeSession = activeSessionForRoute/);
  assert.doesNotMatch(restoreEffect, /\/chat\/sessions"\s*,\s*\{\s*method:\s*"POST"/);
});

test("Learn hides loaded turns and their citations when the selected course changes", () => {
  assert.match(source, /loadedSession\?\.id !== sessionId \|\| loadedSession\.courseId !== courseId/);
  assert.match(source, /visibleTurns\.map\(\(turn, index\).*turn\.citations\.map/);
  assert.match(source, /setTurns\(\(items\) => \[\.\.\.items, \{ role: "student", content, citations: \[\] \}, \{ role: "tutor", content: "", citations: \[\], status: "正在连接学习助手…" \}\]\)/);
});

test("Learn remounts course-scoped state so prior turns, citations, and pending work cannot reappear", () => {
  assert.match(source, /function StudentLearnContent\(\{ courseId \}: \{ courseId: string \}\)/);
  assert.match(source, /const \{ courseId \} = useParams/);
  assert.match(source, /<StudentLearnContent key=\{courseId\} courseId=\{courseId\} \/>/);
  assert.match(source, /const \[turns, setTurns\] = useState<Turn\[]>\(\[\]\)/);
  assert.match(source, /const pendingTurn = useRef<\{ sessionId: string; content: string; selectedPointerId\?: string; clientTurnId: string \} \| null>\(null\)/);
  assert.match(source, /const \[results, setResults\] = useState<SearchItem\[]>\(\[\]\)/);
});

test("Learn saves the newly created session ID in the current URL without reloading", () => {
  const send = source.slice(source.indexOf("async function send"), source.indexOf("return <div className=\"student-learn-page\""));
  assert.match(send, /activeSession = created\.id;\s*loadedSessionRef\.current = \{ id: activeSession, courseId \};\s*setLoadedSession\(\{ id: activeSession, courseId \}\);\s*setRestoreError\(null\);\s*setSessionId\(activeSession\);\s*const currentUrl = new URL\(window\.location\.href\);\s*currentUrl\.searchParams\.set\("session_id", activeSession\);\s*window\.history\.replaceState\(window\.history\.state, "", currentUrl\);/);
  assert.doesNotMatch(send, /location\.reload\(|location\.assign\(/);
});
