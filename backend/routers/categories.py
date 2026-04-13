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

# ============ ACTIVITY CATEGORY ENDPOINTS (NEW) ============


@router.get("/activity-categories")
async def get_activity_categories(current_user: dict = Depends(get_current_user)):
    categories = await db.activity_categories.find({}, {"_id": 0}).to_list(100)
    return categories


@router.post("/activity-categories")
async def create_activity_category(category_data: CategoryCreate, current_user: dict = Depends(get_current_user)):
    # Only SuperUser can create categories
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can create activity categories")
    # Check if category name already exists
    existing = await db.activity_categories.find_one({"name": category_data.name}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Category with this name already exists")
    category = ActivityCategory(
        name=category_data.name,
        created_by=current_user["id"]
    )
    doc = category.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.activity_categories.insert_one(doc)
    return {"message": "Category created successfully", "id": category.id}


@router.delete("/activity-categories/{category_id}")
async def delete_activity_category(category_id: str, current_user: dict = Depends(get_current_user)):
    # Only SuperUser can delete categories
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can delete activity categories")
    result = await db.activity_categories.delete_one({"id": category_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"message": "Category deleted successfully"}
