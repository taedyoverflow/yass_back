from celery import Celery

celery_app = Celery(
    "yass_tasks",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.task_track_started = True

# ✅ Task 모듈 명시적으로 import해서 등록되게 함
import celery_task

# 확인용 강제 출력
print("✅ celery_task 모듈이 import되었습니다.")