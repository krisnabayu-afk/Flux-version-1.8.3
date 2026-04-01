from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Response, Query
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone, timedelta
import uuid
import os
import shutil
import base64
import csv
import io
import math

from database import db, client, UPLOAD_DIR
from utils import get_current_user, get_current_admin, is_tech_op_admin, create_notification, decode_base64_image, verify_password, get_password_hash, create_access_token
from models import *

router = APIRouter()

# ============ SITE MANAGEMENT ENDPOINTS (NEW) ============


@router.post("/sites")
async def create_site(site_data: SiteCreate, current_user: dict = Depends(get_current_user)):
    # FIX 2: All roles (including Staff and SPV) can create sites
    site = Site(
        name=site_data.name,
        cid=site_data.cid,
        location=site_data.location,
        description=site_data.description,
        region=site_data.region,  # REGIONAL
        created_by=current_user["id"]
    )
    doc = site.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.sites.insert_one(doc)
    return {"message": "Site created successfully", "id": site.id}


@router.get("/sites", response_model=PaginatedSiteResponse)
async def get_sites(
    page: int = 1, 
    limit: int = 15,
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    # FIX: Return all sites (including inactive) so they show up in the list
    pipeline = []
    # Add search filter if provided
    if search:
        pipeline.append({
            "$match": {
                "$or": [
                    {"name": {"$regex": search, "$options": "i"}},
                    {"location": {"$regex": search, "$options": "i"}},
                    {"cid": {"$regex": search, "$options": "i"}}
                ]
            }
        })
    # Exclude _id
    pipeline.append({"$project": {"_id": 0}})
    # Pagination logic using $facet
    skip = (page - 1) * limit
    facet_stage = {
        "$facet": {
            "metadata": [{"$count": "total"}],
            "data": [{"$skip": skip}, {"$limit": limit}]
        }
    }
    pipeline.append(facet_stage)
    # Execute aggregation
    result = await db.sites.aggregate(pipeline).to_list(1)
    # Parse result
    metadata = result[0]["metadata"]
    data = result[0]["data"]
    total = metadata[0]["total"] if metadata else 0
    total_pages = (total + limit - 1) // limit if limit > 0 else 0
    return {
        "items": data,
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": total_pages
    }


@router.get("/sites/{site_id}")
async def get_site(site_id: str, current_user: dict = Depends(get_current_user)):
    site = await db.sites.find_one({"id": site_id}, {"_id": 0})
    if not site:
        raise HTTPException(status_code=404, detail="Site not found")
    return site


@router.put("/sites/{site_id}")
async def update_site(site_id: str, site_data: SiteUpdate, current_user: dict = Depends(get_current_user)):
    # FIX 2: All roles (including Staff and SPV) can update sites
    update_dict = {k: v for k, v in site_data.model_dump().items() if v is not None}
    if update_dict:
        await db.sites.update_one(
            {"id": site_id},
            {"$set": update_dict}
        )
    return {"message": "Site updated successfully"}


@router.delete("/sites/{site_id}")
async def delete_site(site_id: str, current_user: dict = Depends(get_current_user)):
    # FIX: Only SuperUser can delete sites
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can delete sites")
    # Hard delete
    result = await db.sites.delete_one({"id": site_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Site not found")
    return {"message": "Site deleted successfully"}
