from fastapi import APIRouter

from app.modules.assessments.router import router as assessments_router
from app.modules.auth.router import router as auth_router
from app.modules.courses.router import router as courses_router
from app.modules.health.router import router as health_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.materials.router import router as materials_router
from app.modules.question_agent.router import router as question_agent_router
from app.modules.tutor.router import router as tutor_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(courses_router, tags=["courses"])
api_router.include_router(materials_router, tags=["materials"])
api_router.include_router(knowledge_router, tags=["knowledge"])
api_router.include_router(assessments_router, tags=["assessments"])
api_router.include_router(question_agent_router, tags=["question-agent"])
api_router.include_router(tutor_router, tags=["tutor"])
