from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from src.control.repositories.analysis_repository import AnalysisRepository
from src.control.schemas.api import PaginatedResponse


router = APIRouter()


@router.get("", response_model=PaginatedResponse)
def list_analysis_runs(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    target_type: str | None = None,
    status: str | None = None,
) -> PaginatedResponse:
    repo = AnalysisRepository(request.app.state.context)
    items, total = repo.list_runs(
        page=page, page_size=page_size, target_type=target_type, status=status,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{run_id}")
def get_analysis_run(run_id: int, request: Request) -> dict:
    repo = AnalysisRepository(request.app.state.context)
    run = repo.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="analysis_run_not_found")
    return run
