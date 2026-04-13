from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from typing import Optional
from datetime import datetime, timezone
import uuid
import os
import shutil

from database import db, UPLOAD_DIR
from utils import get_current_user
from models import TTB, PaginatedTTBResponse

router = APIRouter()


# ============ TTB (Document Archive) ENDPOINTS ============


@router.post("/ttb")
async def upload_ttb(
    site_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a TTB document linked to a site."""
    # Validate site exists
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    site_name = site["name"]
    # Sanitize folder name (same logic as reports)
    folder_name = "".join(c for c in site_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')

    # Create TTB sub-folder inside the site's report folder
    ttb_dir = UPLOAD_DIR / "reports" / folder_name / "TTB"
    ttb_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"ttb_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
    file_path = ttb_dir / unique_filename

    # Save file to disk
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_url = f"/uploads/reports/{folder_name}/TTB/{unique_filename}"

    # Create TTB record
    ttb = TTB(
        site_id=site_id,
        site_name=site_name,
        title=title,
        file_path=str(file_path),
        file_url=file_url,
        file_name=file.filename,
        uploaded_by=current_user["id"],
        uploaded_by_name=current_user["username"]
    )

    doc = ttb.model_dump()
    doc["created_at"] = doc["created_at"].isoformat()
    await db.ttb.insert_one(doc)

    return {"message": "TTB document uploaded successfully", "id": ttb.id}


@router.get("/ttb", response_model=PaginatedTTBResponse)
async def get_ttb_documents(
    page: int = 1,
    limit: int = 15,
    site_id: Optional[str] = None,
    search: Optional[str] = None,
    mine: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    """List all TTB documents with pagination, optional site filter and search."""
    query = {}

    if mine:
        query["uploaded_by"] = current_user["id"]

    if site_id:
        query["site_id"] = site_id

    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"site_name": {"$regex": search, "$options": "i"}},
            {"uploaded_by_name": {"$regex": search, "$options": "i"}}
        ]

    total = await db.ttb.count_documents(query)
    skip = (page - 1) * limit
    total_pages = (total + limit - 1) // limit if limit > 0 else 0

    items = await db.ttb.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


@router.get("/ttb/site/{site_id}")
async def get_ttb_by_site(
    site_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all TTB documents for a specific site (used by SiteDetail)."""
    items = await db.ttb.find({"site_id": site_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return items


@router.delete("/ttb/{ttb_id}")
async def delete_ttb(
    ttb_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a TTB document. Only the uploader or SuperUser can delete."""
    ttb = await db.ttb.find_one({"id": ttb_id}, {"_id": 0})
    if not ttb:
        raise HTTPException(status_code=404, detail="TTB document not found")

    # Authorization: only uploader or SuperUser
    if current_user["id"] != ttb["uploaded_by"] and current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only the uploader or SuperUser can delete this document")

    # Delete file from disk
    try:
        if os.path.exists(ttb["file_path"]):
            os.remove(ttb["file_path"])
    except Exception:
        pass  # File may already be gone

    # Delete from database
    await db.ttb.delete_one({"id": ttb_id})

    return {"message": "TTB document deleted successfully"}
