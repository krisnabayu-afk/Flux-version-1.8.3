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

# ============ USER CREATION ENDPOINT (SuperUser ONLY) ============
@router.post("/users/create", response_model=UserResponse)
async def create_user_direct(user_data: UserCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can create users directly")
        
    existing_user = await db.users.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
        
    # REGIONAL: VP role is exempt from regional constraints (global)
    user_region = None if user_data.role == "VP" else user_data.region
        
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        department=user_data.department,
        division=user_data.division,
        region=user_region,
        account_status="approved"  # Auto-approve for SuperUser created accounts
    )
    
    doc = user.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.users.insert_one(doc)
    
    return UserResponse(**doc)

# ============ USER DELETE ENDPOINT (SuperUser & VP) ============


@router.delete("/users/{user_id}")
async def delete_user(user_id: str, current_user: dict = Depends(get_current_user)):
    # Only SuperUser and VP can delete users
    if current_user["role"] not in ["SuperUser", "VP"]:
        raise HTTPException(status_code=403, detail="Only SuperUser and VP can delete users")
    # Prevent self-deletion
    if user_id == current_user["id"]:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    # VP restriction to department
    if current_user["role"] == "VP":
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        target_department = target_user.get("department")
        # Legacy fallback if department isn't set but we know the division mapping
        if not target_department and target_user.get("division") in ["Monitoring", "Infra", "TS", "Apps", "Fiberzone", "Admin", "Internal Support"]:
            target_department = "Technical Operation"
        if target_department != current_user.get("department"):
            raise HTTPException(status_code=403, detail="VP can only delete users in their own department")
    result = await db.users.delete_one({"id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="User not found")
    return {"message": "User deleted successfully"}


@router.put("/users/{user_id}")
async def update_user_admin(user_id: str, update_data: UserUpdateAdmin, current_user: dict = Depends(get_current_user)):
    # Only SuperUser and VP can update user details
    if current_user["role"] not in ["SuperUser", "VP"]:
        raise HTTPException(status_code=403, detail="Only SuperUser and VP can update user details")
    # VP restriction to department
    if current_user["role"] == "VP":
        target_user = await db.users.find_one({"id": user_id}, {"_id": 0})
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        target_department = target_user.get("department")
        # Legacy fallback if department isn't set but we know the division mapping
        if not target_department and target_user.get("division") in ["Monitoring", "Infra", "TS", "Apps", "Fiberzone", "Admin", "Internal Support"]:
            target_department = "Technical Operation"
        if target_department != current_user.get("department"):
            raise HTTPException(status_code=403, detail="VP can only update users in their own department")
        # Prevent VP from changing users to SuperUser
        if update_data.role == "SuperUser":
             raise HTTPException(status_code=403, detail="VP cannot elevate users to SuperUser")
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    if update_dict:
        await db.users.update_one(
            {"id": user_id},
            {"$set": update_dict}
        )
    return {"message": "User updated successfully"}
# ============ USER ENDPOINTS ============


@router.get("/users", response_model=List[UserResponse])
async def get_users(current_user: dict = Depends(get_current_user)):
    # SuperUser sees all users
    if current_user["role"] == "SuperUser":
        query = {}
    else:
        # Others see only approved users
        query = {"account_status": "approved"}
    # Managers/SPV/Staff see all approved users by default (removed division/region restriction)
    pass # No additional filtering for Managers/SPV beyond account_status here
    # DEPARTMENT: Filter users for VPs with a department
    if current_user["role"] == "VP":
        # First, allow VPs to see all users in their department, regardless of account_status (like SuperUser)
        query.pop("account_status", None)
        dept_name = current_user.get("department")
        # Fallback to division mapping if department is missing
        if not dept_name and current_user.get("division") in ["Monitoring", "Infra", "TS", "Apps", "Fiberzone", "Admin", "Internal Support"]:
            dept_name = "Technical Operation"
            
        if dept_name:
            dept = await db.departments.find_one({"name": dept_name})
            target_divisions = dept.get("divisions", []) if dept else []
            
            if target_divisions:
                 query["$or"] = [
                     {"department": dept_name},
                     {"department": None, "division": {"$in": target_divisions}},
                     {"department": {"$exists": False}, "division": {"$in": target_divisions}}
                 ]
            else:
                 query["department"] = dept_name
        else:
            # If VP somehow has no department and an unrecognized division, restrict to ONLY themselves
            query["id"] = current_user["id"]
        # Security: VP should absolutely never see a SuperUser in their query results
        query["role"] = {"$ne": "SuperUser"}
    users = await db.users.find(query, {"_id": 0, "password_hash": 0, "profile_photo": 0}).to_list(1000)
    return [UserResponse(**user) for user in users]


@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user_detail(user_id: str, current_user: dict = Depends(get_current_user)):
    user = await db.users.find_one({"id": user_id}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return UserResponse(**user)


@router.get("/users/by-division/{division}", response_model=List[UserResponse])
async def get_users_by_division(division: str, current_user: dict = Depends(get_current_user)):
    users = await db.users.find({"division": division, "account_status": "approved"}, {"_id": 0, "password_hash": 0, "profile_photo": 0}).to_list(1000)
    return [UserResponse(**user) for user in users]
