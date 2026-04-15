from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.control.schemas.api import GroupPatch, PaginatedResponse
from src.control.services.group_service import GroupService


router = APIRouter()


@router.get("", response_model=PaginatedResponse)
def list_groups(request: Request, page: int = 1) -> PaginatedResponse:
    service = GroupService(request.app.state.context)
    items, total = service.list_groups(page=page)
    return PaginatedResponse(items=items, total=total, page=page)


@router.patch("/{group_id}")
def update_group(group_id: str, patch: GroupPatch, request: Request) -> dict:
    service = GroupService(request.app.state.context)
    try:
        group = service.update_group(group_id, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="group_not_found") from exc

    return group.model_dump(mode="json")


@router.delete("/{group_id}")
def delete_group(group_id: str, request: Request) -> dict:
    ctx = request.app.state.context
    group = ctx.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    with ctx._lock:
        ctx._conn.execute("DELETE FROM groups WHERE group_id = ?", (group_id,))
        ctx._conn.execute("DELETE FROM group_members WHERE group_id = ?", (group_id,))
        ctx._conn.execute("DELETE FROM proactive_chats WHERE id = ?", (group_id,))
        ctx._conn.commit()
    return {"deleted": True, "group_id": group_id}


@router.get("/{group_id}")
def get_group(group_id: str, request: Request) -> dict:
    group = request.app.state.context.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")
    return group.model_dump(mode="json")


@router.post("/{group_id}/analyze")
def analyze_group(group_id: str, request: Request) -> dict:
    from src.control.services.analysis_service import AnalysisService

    group = request.app.state.context.get_group(group_id)
    if not group:
        raise HTTPException(status_code=404, detail="group_not_found")

    service = AnalysisService(request.app.state.context, style_dir=str(request.app.state.style_dir))
    run = service.run_analysis(target_type="group", target_id=group_id, trigger_type="manual")
    return {"analysis_run_id": run["id"], "status": run["status"]}
