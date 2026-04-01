from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.control.repositories.review_repository import ReviewRepository
from src.control.schemas.api import PaginatedResponse
from src.control.services.review_service import ReviewService


class ApplyEditedRequest(BaseModel):
    edited_payload: dict


router = APIRouter()


@router.get("", response_model=PaginatedResponse)
def list_reviews(
    request: Request,
    page: int = 1,
    page_size: int = 20,
    status: str | None = None,
    target_type: str | None = None,
    review_type: str | None = None,
) -> PaginatedResponse:
    repo = ReviewRepository(request.app.state.context)
    items, total = repo.list_items(
        page=page, page_size=page_size,
        status=status, target_type=target_type, review_type=review_type,
    )
    return PaginatedResponse(items=items, page=page, page_size=page_size, total=total)


@router.get("/{item_id}")
def get_review(item_id: int, request: Request) -> dict:
    repo = ReviewRepository(request.app.state.context)
    item = repo.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="review_item_not_found")
    return item


@router.post("/{item_id}/approve")
def approve_review(item_id: int, request: Request) -> dict:
    service = ReviewService(request.app.state.context, style_dir=str(request.app.state.style_dir))
    try:
        return service.approve(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="review_item_not_found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.post("/{item_id}/reject")
def reject_review(item_id: int, request: Request) -> dict:
    service = ReviewService(request.app.state.context, style_dir=str(request.app.state.style_dir))
    try:
        return service.reject(item_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="review_item_not_found")


@router.post("/{item_id}/apply-edited")
def apply_edited(item_id: int, body: ApplyEditedRequest, request: Request) -> dict:
    service = ReviewService(request.app.state.context, style_dir=str(request.app.state.style_dir))
    try:
        return service.apply_edited(item_id, body.edited_payload)
    except KeyError:
        raise HTTPException(status_code=404, detail="review_item_not_found")
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
