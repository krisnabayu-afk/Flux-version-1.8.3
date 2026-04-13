from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from typing import Optional
from datetime import datetime, timezone
import uuid
import os
import shutil

from database import db, UPLOAD_DIR
from utils import get_current_user
from models import Documentation, PaginatedDocumentationResponse

router = APIRouter()

# ============ DOCUMENTATION ENDPOINTS ============

@router.post("/documentation")
async def upload_documentation(
    site_id: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    """Upload a Documentation file linked to a site."""
    # Validate site exists
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")

    site_name = site["name"]
    # Sanitize folder name
    folder_name = "".join(c for c in site_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')

    # Create documentation sub-folder inside the site's report folder
    doc_dir = UPLOAD_DIR / "reports" / folder_name / "documentation"
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Generate unique filename
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"doc_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
    file_path = doc_dir / unique_filename

    # Save file to disk
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    file_url = f"/uploads/reports/{folder_name}/documentation/{unique_filename}"

    # Create Documentation record
    doc = Documentation(
        site_id=site_id,
        site_name=site_name,
        title=title,
        file_path=str(file_path),
        file_url=file_url,
        file_name=file.filename,
        uploaded_by=current_user["id"],
        uploaded_by_name=current_user["username"]
    )

    doc_data = doc.model_dump()
    doc_data["created_at"] = doc_data["created_at"].isoformat()
    await db.documentation.insert_one(doc_data)

    return {"message": "Documentation uploaded successfully", "id": doc.id}


@router.get("/documentation", response_model=PaginatedDocumentationResponse)
async def get_documentations(
    page: int = 1,
    limit: int = 15,
    site_id: Optional[str] = None,
    search: Optional[str] = None,
    mine: bool = Query(False),
    current_user: dict = Depends(get_current_user)
):
    """List all Documentation files with pagination, optional site filter and search."""
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

    total = await db.documentation.count_documents(query)
    skip = (page - 1) * limit
    total_pages = (total + limit - 1) // limit if limit > 0 else 0

    items = await db.documentation.find(query, {"_id": 0}).sort("created_at", -1).skip(skip).limit(limit).to_list(limit)

    return {
        "items": items,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


@router.get("/documentation/site/{site_id}")
async def get_documentation_by_site(
    site_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get all documentation files for a specific site (used by SiteDetail)."""
    items = await db.documentation.find({"site_id": site_id}, {"_id": 0}).sort("created_at", -1).to_list(None)
    return items


@router.delete("/documentation/{doc_id}")
async def delete_documentation(
    doc_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a Documentation file. Only the uploader or SuperUser can delete."""
    doc = await db.documentation.find_one({"id": doc_id}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Documentation not found")

    # Authorization: only uploader or SuperUser
    if current_user["id"] != doc["uploaded_by"] and current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only the uploader or SuperUser can delete this document")

    # Delete file from disk
    try:
        if os.path.exists(doc["file_path"]):
            os.remove(doc["file_path"])
    except Exception:
        pass  # File may already be gone

    # Delete from database
    await db.documentation.delete_one({"id": doc_id})

    return {"message": "Documentation deleted successfully"}
