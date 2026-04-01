from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from src.control.bootstrap import bootstrap_rules_if_empty, recover_stale_runs
from src.control.api.routes.analyses import router as analyses_router
from src.control.api.routes.contacts import router as contacts_router
from src.control.api.routes.dashboard import router as dashboard_router
from src.control.api.routes.group_members import router as group_members_router
from src.control.api.routes.groups import router as groups_router
from src.control.api.routes.reviews import router as reviews_router
from src.control.api.routes.rules import router as rules_router
from src.control.api.routes.messages import router as messages_router
from src.control.api.routes.proactive import router as proactive_router
from src.control.api.routes.runtime import router as runtime_router
from src.control.api.routes.scheduler import router as scheduler_router
from src.core.context import ContextManager
from src.core.style import StyleManager


def create_control_app(
    db_path: str = "data/agent.db",
    style_dir: str = "styles",
) -> FastAPI:
    app = FastAPI(title="WeChatAgent Control API")

    app.state.context = ContextManager(Path(db_path))
    app.state.style_dir = Path(style_dir)
    app.state.style_manager = StyleManager(Path(style_dir))
    bootstrap_rules_if_empty(app.state.context, Path(style_dir))
    recover_stale_runs(app.state.context)

    app.include_router(dashboard_router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(contacts_router, prefix="/api/contacts", tags=["contacts"])
    app.include_router(groups_router, prefix="/api/groups", tags=["groups"])
    app.include_router(group_members_router, prefix="/api/groups", tags=["group-members"])
    app.include_router(rules_router, prefix="/api/rules", tags=["rules"])
    app.include_router(analyses_router, prefix="/api/analysis-runs", tags=["analyses"])
    app.include_router(reviews_router, prefix="/api/reviews", tags=["reviews"])
    app.include_router(scheduler_router, prefix="/api/scheduler", tags=["scheduler"])
    app.include_router(messages_router, prefix="/api/messages", tags=["messages"])
    app.include_router(proactive_router, prefix="/api/proactive-chats", tags=["proactive"])
    app.include_router(runtime_router, prefix="/api/runtime", tags=["runtime"])

    # Serve frontend static files
    static_dir = Path(__file__).resolve().parents[3] / "static"
    if static_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(static_dir / "assets")), name="static")

        @app.get("/{path:path}")
        async def serve_spa(path: str):
            """Serve the SPA index.html for all non-API routes."""
            return FileResponse(str(static_dir / "index.html"))

    return app
