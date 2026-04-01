from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.control.services.rule_service import RuleService


class RuleUpsertRequest(BaseModel):
    document: dict


router = APIRouter()


def _service(request: Request) -> RuleService:
    return RuleService(request.app.state.context, request.app.state.style_dir)


@router.get("/default")
def get_default_rule(request: Request) -> dict:
    rule = _service(request).get_rule("global", "__global__")
    if not rule:
        raise HTTPException(status_code=404, detail="rule_not_found")
    return rule


@router.put("/default")
def put_default_rule(payload: RuleUpsertRequest, request: Request) -> dict:
    return _service(request).upsert_rule(
        scope_type="global",
        scope_id="__global__",
        document=payload.document,
    )


@router.get("/private/{wxid}")
def get_private_rule(wxid: str, request: Request) -> dict:
    rule = _service(request).get_rule("contact", wxid)
    if not rule:
        raise HTTPException(status_code=404, detail="rule_not_found")
    return rule


@router.put("/private/{wxid}")
def put_private_rule(wxid: str, payload: RuleUpsertRequest, request: Request) -> dict:
    return _service(request).upsert_rule(
        scope_type="contact",
        scope_id=wxid,
        document=payload.document,
    )


@router.get("/group/{group_id}")
def get_group_rule(group_id: str, request: Request) -> dict:
    rule = _service(request).get_rule("group", group_id)
    if not rule:
        raise HTTPException(status_code=404, detail="rule_not_found")
    return rule


@router.put("/group/{group_id}")
def put_group_rule(group_id: str, payload: RuleUpsertRequest, request: Request) -> dict:
    return _service(request).upsert_rule(
        scope_type="group",
        scope_id=group_id,
        document=payload.document,
    )
