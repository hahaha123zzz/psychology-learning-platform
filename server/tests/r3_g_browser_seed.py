import json
import time

from conftest import create_user_sync

stamp = str(time.time_ns())
teacher_email = f"r3-g-teacher-{stamp}@example.org"
student_email = f"r3-g-student-{stamp}@example.org"
password = "r3-g-browser-test-password"
student_id = create_user_sync(email=student_email, password=password)
create_user_sync(email=teacher_email, password=password, is_teacher=True)

print(
    json.dumps(
        {
            "teacher_email": teacher_email,
            "student_email": student_email,
            "password": password,
            "student_id": student_id,
        }
    )
)
