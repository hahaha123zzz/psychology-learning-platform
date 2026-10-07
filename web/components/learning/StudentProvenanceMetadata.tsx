import type { StudentProvenance } from "../../lib/student-provenance";
import { studentCourseResourceRoleLabel, studentProvenanceStatusLabel } from "../../lib/student-provenance";

function valueOrUnavailable(value: string | null): string {
  return value ?? "未提供";
}

export default function StudentProvenanceMetadata({ provenance }: { provenance: StudentProvenance | null }) {
  if (!provenance) {
    return (
      <section className="student-provenance" aria-label="来源信息">
        <strong role="status">来源信息未提供</strong>
        <p>课程用途未分类</p>
      </section>
    );
  }

  return (
    <section className="student-provenance" aria-label="来源信息">
      <strong>{studentProvenanceStatusLabel(provenance.status)}</strong>
      <dl>
        <div><dt>来源标题</dt><dd>{valueOrUnavailable(provenance.source_title)}</dd></div>
        <div><dt>发布方</dt><dd>{valueOrUnavailable(provenance.publisher)}</dd></div>
        <div><dt>内容作者</dt><dd>{valueOrUnavailable(provenance.content_author)}</dd></div>
        <div><dt>版次</dt><dd>{valueOrUnavailable(provenance.edition)}</dd></div>
        <div><dt>来源网址</dt><dd>{valueOrUnavailable(provenance.source_url)}</dd></div>
        <div><dt>许可信息</dt><dd>{valueOrUnavailable(provenance.license)}</dd></div>
        <div><dt>课程用途</dt><dd>{studentCourseResourceRoleLabel(provenance.course_resource_role)}</dd></div>
        <div><dt>来源信息版本</dt><dd>{provenance.version}</dd></div>
      </dl>
    </section>
  );
}
