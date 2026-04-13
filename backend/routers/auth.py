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

# ============ AUTH ENDPOINTS ============


@router.post("/auth/register", response_model=UserResponse)
async def register(user_data: UserCreate):
    # Validate email domain - only @varnion.net.id and @fiberzone.id allowed
    allowed_domains = ("@varnion.net.id", "@fiberzone.id")
    if not user_data.email.lower().endswith(allowed_domains):
        raise HTTPException(status_code=400, detail="Only @varnion.net.id and @fiberzone.id email addresses are allowed for registration")
    existing_user = await db.users.find_one({"email": user_data.email}, {"_id": 0})
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    # NEW: Validate that Apps and Fiberzone can only be Staff
    if user_data.division in ["Apps", "Fiberzone"] and user_data.role != "Staff":
        raise HTTPException(status_code=400, detail="Apps and Fiberzone divisions can only register as Staff")
    # DEPARTMENT: Validate department is required
    if not user_data.department:
        raise HTTPException(status_code=400, detail="Department is required")
    # Validate division is required
    if not user_data.division:
        raise HTTPException(status_code=400, detail="Division is required")
    # DEPARTMENT: Validate division belongs to the selected department
    dept = await db.departments.find_one({"name": user_data.department})
    if not dept:
        raise HTTPException(
            status_code=400,
            detail=f"Department '{user_data.department}' does not exist"
        )
    
    allowed_divisions = dept.get("divisions", [])
    if user_data.division not in allowed_divisions:
        raise HTTPException(
            status_code=400,
            detail=f"Division '{user_data.division}' is not valid for department '{user_data.department}'. Allowed: {', '.join(allowed_divisions)}"
        )
    # REGIONAL: Validate region requirement for non-VP roles
    if user_data.role != "VP" and not user_data.region:
        raise HTTPException(status_code=400, detail="Region is required for non-VP roles")
    # REGIONAL: VP role is exempt from regional constraints (set to None for global view)
    user_region = None if user_data.role == "VP" else user_data.region
    # NEW: Staff, SPV and Manager registrations are pending by default
    account_status = "pending" if user_data.role in ["Staff", "SPV", "Manager"] else "approved"
    user = User(
        username=user_data.username,
        email=user_data.email,
        password_hash=get_password_hash(user_data.password),
        role=user_data.role,
        department=user_data.department,
        division=user_data.division,
        region=user_region,
        account_status=account_status
    )
    doc = user.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    await db.users.insert_one(doc)
    # NEW: Notify appropriate approver
    if user_data.role in ["Staff", "SPV"] and user_data.division:
        # Determine target division for approval
        target_division = user_data.division
        if user_data.department == "Technical Operation":
            if user_data.division == "Apps":
                target_division = "TS"
            elif user_data.division == "Fiberzone":
                target_division = "Infra"
        manager = await db.users.find_one({"role": "Manager", "division": target_division}, {"_id": 0})
        if manager:
            await create_notification(
                user_id=manager["id"],
                title="New Person need Action",
                message=f"{user_data.username} Just Registered! ({user_data.role} - {user_data.division}) Please take an Action",
                notification_type="account_approval",
                related_id=user.id
            )
    elif user_data.role == "Manager":
        # DEPARTMENT: VP lookup filtered by department
        vp_query = {"role": "VP", "account_status": "approved"}
        if user_data.department:
            vp_query["department"] = user_data.department
        vp = await db.users.find_one(vp_query, {"_id": 0})
        if vp:
            await create_notification(
                user_id=vp["id"],
                title="New Manager Has Been Registered",
                message=f"{user_data.username} (Manager - {user_data.department}) has registered and needs action",
                notification_type="account_approval",
                related_id=user.id
            )
    return UserResponse(
        id=user.id,
        username=user.username,
        email=user.email,
        role=user.role,
        department=user.department,
        division=user.division,
        region=user.region,
        account_status=account_status,
        profile_photo=None,
        telegram_id=None
    )


@router.post("/auth/login", response_model=TokenResponse)
async def login(credentials: UserLogin):
    user = await db.users.find_one({"email": credentials.email}, {"_id": 0})
    if not user or not verify_password(credentials.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    # NEW: Check account status
    if user.get("account_status") == "pending":
        raise HTTPException(status_code=403, detail="Account pending approval")
    if user.get("account_status") == "rejected":
        raise HTTPException(status_code=403, detail="Account has been rejected")
    access_token = create_access_token(data={"sub": user["id"]})
    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        user=UserResponse(
            id=user["id"],
            username=user["username"],
            email=user["email"],
            role=user["role"],
            department=user.get("department"),
            division=user.get("division"),
            region=user.get("region"),
            account_status=user.get("account_status"),
            profile_photo=user.get("profile_photo"),
            telegram_id=user.get("telegram_id")
        )
    )


@router.get("/auth/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return UserResponse(
        id=current_user["id"],
        username=current_user["username"],
        email=current_user["email"],
        role=current_user["role"],
        department=current_user.get("department"),
        division=current_user.get("division"),
        region=current_user.get("region"),
        account_status=current_user.get("account_status"),
        profile_photo=current_user.get("profile_photo"),
        telegram_id=current_user.get("telegram_id")
    )
# NEW: Profile Management


@router.put("/auth/profile")
async def update_profile(profile_data: UserProfileUpdate, current_user: dict = Depends(get_current_user)):
    update_dict: dict[str, Any] = {}
    if profile_data.username:
        update_dict["username"] = profile_data.username
    if profile_data.telegram_id is not None:
        update_dict["telegram_id"] = profile_data.telegram_id
    if profile_data.new_password:
        if not profile_data.current_password or not profile_data.confirm_password:
            raise HTTPException(status_code=400, detail="Current password and confirmation required")
        if not verify_password(profile_data.current_password, current_user["password_hash"]):
            raise HTTPException(status_code=400, detail="Current password is incorrect")
        if profile_data.new_password != profile_data.confirm_password:
            raise HTTPException(status_code=400, detail="Passwords do not match")
        update_dict["password_hash"] = get_password_hash(profile_data.new_password)
    if update_dict:
        await db.users.update_one(
            {"id": current_user["id"]},
            {"$set": update_dict}
        )
    return {"message": "Profile updated successfully"}


@router.post("/auth/profile/photo")
async def upload_profile_photo(
    photo: UploadFile = File(...),
    current_user: dict = Depends(get_current_user)
):
    # Read file and encode to base64
    file_content = await photo.read()
    photo_data = base64.b64encode(file_content).decode('utf-8')
    await db.users.update_one(
        {"id": current_user["id"]},
        {"$set": {"profile_photo": photo_data}}
    )
    return {"message": "Profile photo updated successfully", "photo_data": photo_data}
# NEW: Account Approval Endpoints


@router.get("/accounts/pending")
async def get_pending_accounts(current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["Manager", "VP"]:
        raise HTTPException(status_code=403, detail="Only managers and VP can view pending accounts")
    # DEPARTMENT: Admin division cannot perform staff approvals
    if current_user.get("division") == "Admin":
        return []
    if current_user["role"] == "Manager":
        query = {"account_status": "pending"}
        user_division = current_user.get("division")
        user_dept = current_user.get("department")
        # Build division filter to include sub-divisions
        division_filter = [user_division]
        if user_dept == "Technical Operation":
            if user_division == "TS":
                division_filter.append("Apps")
            elif user_division == "Infra":
                division_filter.append("Fiberzone")
        query["division"] = {"$in": division_filter}
        # FIX: Managers cannot see pending Manager accounts
        query["role"] = {"$ne": "Manager"}
        # REGIONAL: Support linear approval workflow
        # Manager only sees "pending" users in their REGION
        if current_user.get("region"):
            query["region"] = current_user.get("region")
    elif current_user["role"] == "VP":
        # VP only needs to approve Manager accounts in their department
        query = {"account_status": "pending", "role": "Manager"}
        # DEPARTMENT: VP can only see Managers in their own department
        if current_user.get("department"):
            query["department"] = current_user.get("department")
    pending_users = await db.users.find(query, {"_id": 0, "password_hash": 0}).to_list(1000)
    return pending_users


@router.post("/accounts/review")
async def review_account(action_data: AccountApprovalAction, current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["Manager", "VP"]:
        raise HTTPException(status_code=403, detail="Only managers and VP can review accounts")
    # DEPARTMENT: Admin division cannot perform staff approvals
    if current_user.get("division") == "Admin":
        raise HTTPException(status_code=403, detail="Users in Admin division cannot perform staff approvals")
    user = await db.users.find_one({"id": action_data.user_id}, {"_id": 0})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user["role"] == "Manager":
        user_division = current_user.get("division")
        target_user_division = user.get("division")
        # Check if manager can review this user
        allowed = False
        if target_user_division == user_division:
            allowed = True
        elif current_user.get("department") == "Technical Operation":
            if user_division == "TS" and target_user_division == "Apps":
                allowed = True
            elif user_division == "Infra" and target_user_division == "Fiberzone":
                allowed = True
        if not allowed:
            raise HTTPException(status_code=403, detail="Can only review accounts from your division or its sub-divisions")
        # REGIONAL: Regional restriction for Manager
        user_region = current_user.get("region")
        target_user_region = user.get("region")
        if user_region and target_user_region and user_region != target_user_region:
            raise HTTPException(status_code=403, detail="Can only review accounts from your region")
        # FIX: Managers cannot review Manager accounts
        if user.get("role") == "Manager":
            raise HTTPException(status_code=403, detail="Managers cannot review other Manager accounts")
        # Manager approval is now FINAL for Staff/SPV
        if action_data.action == "approve":
             new_status = "approved"
        else:
             new_status = "rejected"
    elif current_user["role"] == "VP":
        # VP approves to 'approved'
        if action_data.action == "approve":
             new_status = "approved"
        else:
             new_status = "rejected"
        # DEPARTMENT: VP can only review Manager accounts in their own department
        if current_user.get("department") and user.get("department") and current_user.get("department") != user.get("department"):
            raise HTTPException(status_code=403, detail="VP can only review accounts from their own department")
    # Update status
    await db.users.update_one(
        {"id": action_data.user_id},
        {"$set": {"account_status": new_status}}
    )
    # Notify User
    await create_notification(
        user_id=action_data.user_id,
        title=f"Your Account {new_status.capitalize()}",
        message=f"Your account has been {new_status} by {current_user['username']}",
        notification_type="account_status"
    )
    return {"message": f"Account {new_status}"}
