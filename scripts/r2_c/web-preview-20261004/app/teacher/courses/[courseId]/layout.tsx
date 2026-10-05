import type { ReactNode } from "react";
import CourseShell from "../../../../components/CourseShell";

export default function TeacherCourseLayout({ children }: { children: ReactNode }) { return <CourseShell role="teacher">{children}</CourseShell>; }
