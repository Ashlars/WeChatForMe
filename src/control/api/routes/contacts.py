from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

import re

from src.control.schemas.api import ContactPatch, PaginatedResponse
from src.control.services.contact_service import ContactService


router = APIRouter()


@router.post("/cleanup")
def cleanup_contacts(request: Request) -> dict:
    """Scan and remove invalid/duplicate contacts."""
    conn = request.app.state.context._conn
    rows = conn.execute("SELECT wxid, nickname FROM contacts").fetchall()

    removed = []
    for r in rows:
        wxid = r["wxid"]
        nickname = r["nickname"] or ""

        # Rule 1: pure numeric wxid (likely parsing errors)
        if re.fullmatch(r"\d+", wxid):
            removed.append({"wxid": wxid, "nickname": nickname, "reason": "纯数字wxid"})
            continue

        # Rule 2: wxid equals nickname (likely used name as wxid by mistake)
        if wxid == nickname and not wxid.startswith("wxid_"):
            # Check if a real wxid exists for this name
            dup = conn.execute(
                "SELECT wxid FROM contacts WHERE nickname = ? AND wxid != ?",
                (nickname, wxid),
            ).fetchone()
            if dup:
                removed.append({"wxid": wxid, "nickname": nickname, "reason": f"重复 (真实wxid: {dup['wxid']})"})
                continue

    if removed:
        wxids = [r["wxid"] for r in removed]
        placeholders = ",".join("?" * len(wxids))
        conn.execute(f"DELETE FROM contacts WHERE wxid IN ({placeholders})", wxids)
        conn.execute(f"DELETE FROM group_members WHERE wxid IN ({placeholders})", wxids)
        conn.execute(f"DELETE FROM messages WHERE contact_id IN ({placeholders})", wxids)
        conn.commit()

    return {"removed": removed, "removed_count": len(removed)}


@router.get("", response_model=PaginatedResponse)
def list_contacts(request: Request) -> PaginatedResponse:
    service = ContactService(request.app.state.context)
    items, total = service.list_contacts()
    return PaginatedResponse(items=items, total=total)


@router.patch("/{wxid}")
def update_contact(wxid: str, patch: ContactPatch, request: Request) -> dict:
    service = ContactService(request.app.state.context)
    try:
        contact = service.update_contact(wxid, patch)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="contact_not_found") from exc

    return contact.model_dump(mode="json")


@router.delete("/{wxid}")
def delete_contact(wxid: str, request: Request) -> dict:
    conn = request.app.state.context._conn
    contact = request.app.state.context.get_contact(wxid)
    if not contact:
        raise HTTPException(status_code=404, detail="contact_not_found")
    conn.execute("DELETE FROM contacts WHERE wxid = ?", (wxid,))
    conn.execute("DELETE FROM group_members WHERE wxid = ?", (wxid,))
    conn.commit()
    return {"deleted": True, "wxid": wxid}


@router.get("/{wxid}")
def get_contact(wxid: str, request: Request) -> dict:
    contact = request.app.state.context.get_contact(wxid)
    if not contact:
        raise HTTPException(status_code=404, detail="contact_not_found")
    return contact.model_dump(mode="json")


@router.post("/{wxid}/analyze")
def analyze_contact(wxid: str, request: Request) -> dict:
    from src.control.services.analysis_service import AnalysisService

    contact = request.app.state.context.get_contact(wxid)
    if not contact:
        raise HTTPException(status_code=404, detail="contact_not_found")

    service = AnalysisService(request.app.state.context, style_dir=str(request.app.state.style_dir))
    run = service.run_analysis(target_type="contact", target_id=wxid, trigger_type="manual")
    return {"analysis_run_id": run["id"], "status": run["status"]}
