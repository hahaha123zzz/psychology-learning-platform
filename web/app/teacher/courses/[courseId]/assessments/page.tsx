"use client";

import { useParams } from "next/navigation";
import TeacherAssessments from "../../../../../components/TeacherAssessments";

export default function AssessmentsPage() {
  const { courseId } = useParams<{ courseId: string }>();
  return <TeacherAssessments embedded initialCourseId={courseId} />;
}
