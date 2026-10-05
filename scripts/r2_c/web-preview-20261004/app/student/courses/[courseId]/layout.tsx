import type { ReactNode } from "react";
import CourseShell from "../../../../components/CourseShell";

export default function StudentCourseLayout({ children }: { children: ReactNode }) { return <CourseShell role="student">{children}</CourseShell>; }
