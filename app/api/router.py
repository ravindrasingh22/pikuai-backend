from fastapi import APIRouter, Depends

from app.core.security import require_parent_or_admin
from app.modules.admin.router import router as admin_router
from app.modules.alerts.router import router as alerts_router
from app.modules.auth.router import router as auth_router
from app.modules.billing.router import router as billing_router
from app.modules.chat.router import router as chat_router
from app.modules.children.router import router as children_router
from app.modules.controls.router import router as controls_router
from app.modules.dashboard.router import router as dashboard_router
from app.modules.explainability.router import router as explainability_router
from app.modules.llm.router import router as llm_router
from app.modules.notifications.router import router as notifications_router
from app.modules.parent.router import router as parent_router
from app.modules.privacy.router import router as privacy_router
from app.modules.reports.router import router as reports_router
from app.modules.transcripts.router import router as transcripts_router
from app.modules.trust.router import router as trust_router

api_router = APIRouter()

api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
parent_dependencies = [Depends(require_parent_or_admin)]

api_router.include_router(parent_router, prefix="/parent", tags=["parent"], dependencies=parent_dependencies)
api_router.include_router(children_router, prefix="/children", tags=["children"], dependencies=parent_dependencies)
api_router.include_router(controls_router, prefix="/controls", tags=["controls"], dependencies=parent_dependencies)
api_router.include_router(privacy_router, prefix="/privacy", tags=["privacy"], dependencies=parent_dependencies)
api_router.include_router(billing_router, prefix="/billing", tags=["billing"], dependencies=parent_dependencies)
api_router.include_router(chat_router, prefix="/chat", tags=["chat"], dependencies=parent_dependencies)
api_router.include_router(dashboard_router, prefix="/dashboard", tags=["dashboard"], dependencies=parent_dependencies)
api_router.include_router(transcripts_router, prefix="/transcripts", tags=["transcripts"], dependencies=parent_dependencies)
api_router.include_router(alerts_router, prefix="/alerts", tags=["alerts"], dependencies=parent_dependencies)
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"], dependencies=parent_dependencies)
api_router.include_router(explainability_router, prefix="/explainability", tags=["explainability"], dependencies=parent_dependencies)
api_router.include_router(reports_router, prefix="/reports", tags=["reports"], dependencies=parent_dependencies)
api_router.include_router(llm_router, prefix="/llm", tags=["llm"])
api_router.include_router(trust_router, prefix="/trust", tags=["trust"])
