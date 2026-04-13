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

# ============ HOLIDAY MANAGEMENT ENDPOINTS (NEW) ============


@router.get("/holidays")
async def get_holidays():
    holidays = await db.holidays.find({}, {"_id": 0}).to_list(1000)
    return holidays


@router.post("/holidays")
async def create_holiday(holiday_data: HolidayCreate, current_user: dict = Depends(get_current_user)):
    if not is_tech_op_admin(current_user):
        raise HTTPException(status_code=403, detail="Only Tech Op Admin or VP can manage holidays")
    # Default end_date to start_date if not provided
    end_date = holiday_data.end_date or holiday_data.start_date
    # Check if a holiday already exists for this exact range (simplified check)
    existing = await db.holidays.find_one({"start_date": holiday_data.start_date, "end_date": end_date})
    if existing:
        raise HTTPException(status_code=400, detail="Holiday already exists for this date range")
    holiday = Holiday(
        start_date=holiday_data.start_date,
        end_date=end_date,
        description=holiday_data.description,
        is_recurring=holiday_data.is_recurring,
        created_by=current_user["id"]
    )
    doc = holiday.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.holidays.insert_one(doc)
    return holiday


@router.put("/holidays/{holiday_id}")
async def update_holiday(holiday_id: str, holiday_data: HolidayCreate, current_user: dict = Depends(get_current_user)):
    if not is_tech_op_admin(current_user):
        raise HTTPException(status_code=403, detail="Only Tech Op Admin or VP can manage holidays")
    existing = await db.holidays.find_one({"id": holiday_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Holiday not found")
    update_dict = holiday_data.model_dump()
    if not update_dict.get("end_date"):
        update_dict["end_date"] = holiday_data.start_date
    await db.holidays.update_one({"id": holiday_id}, {"$set": update_dict})
    return {"message": "Holiday updated successfully"}


@router.delete("/holidays/{holiday_id}")
async def delete_holiday(holiday_id: str, current_user: dict = Depends(get_current_user)):
    if not is_tech_op_admin(current_user):
        raise HTTPException(status_code=403, detail="Only Tech Op Admin or VP can manage holidays")
    result = await db.holidays.delete_one({"id": holiday_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Holiday not found")
    return {"message": "Holiday deleted successfully"}
