from fastapi import APIRouter

from app.modules.analytics.router import router as analytics_router
from app.modules.assessments.router import router as assessments_router
from app.modules.auth.router import router as auth_router
from app.modules.cases.router import router as cases_router
from app.modules.courses.router import router as courses_router
from app.modules.health.router import router as health_router
from app.modules.interventions.router import router as interventions_router
from app.modules.knowledge.router import router as knowledge_router
from app.modules.labs.router import router as labs_router
from app.modules.learning_events.router import router as learning_events_router
from app.modules.materials.router import router as materials_router
from app.modules.memory.router import router as memory_router
from app.modules.question_agent.router import router as question_agent_router
from app.modules.teaching_activities.router import router as teaching_activities_router
from app.modules.teaching_assets.router import router as teaching_assets_router
from app.modules.tutor.router import router as tutor_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router, tags=["auth"])
api_router.include_router(cases_router, tags=["cases"])
api_router.include_router(courses_router, tags=["courses"])
api_router.include_router(materials_router, tags=["materials"])
api_router.include_router(knowledge_router, tags=["knowledge"])
api_router.include_router(learning_events_router, tags=["learning-events"])
api_router.include_router(labs_router, tags=["labs"])
api_router.include_router(interventions_router, tags=["interventions"])
api_router.include_router(assessments_router, tags=["assessments"])
api_router.include_router(question_agent_router, tags=["question-agent"])
api_router.include_router(memory_router, tags=["memory"])
api_router.include_router(tutor_router, tags=["tutor"])
api_router.include_router(teaching_assets_router, tags=["teaching-assets"])
api_router.include_router(teaching_activities_router, tags=["teaching-activities"])
api_router.include_router(analytics_router, tags=["analytics"])
