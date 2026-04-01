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

# ============ DASHBOARD ENDPOINT ============


@router.get("/dashboard")
async def get_dashboard(current_user: dict = Depends(get_current_user)):
    today = datetime.now(timezone.utc)
    today_str = today.isoformat()
    schedules_today = await db.schedules.find(
        {"user_id": current_user["id"]},
        {"_id": 0}
    ).to_list(100)
    schedules_today = [
        s for s in schedules_today 
        if datetime.fromisoformat(s["start_date"]).date() <= today.date() <= datetime.fromisoformat(s["end_date"]).date()
    ]

    # WEEKLY COUNTS (NEW)
    # Get all user's schedules for the current week (Monday to Sunday)
    start_of_week = today - timedelta(days=today.weekday()) # Monday
    weekly_counts = []
    all_user_schedules = await db.schedules.find(
        {"user_id": current_user["id"]},
        {"_id": 0, "start_date": 1, "end_date": 1}
    ).to_list(1000)

    for i in range(7):
        day = start_of_week + timedelta(days=i)
        day_date = day.date()
        count = 0
        for s in all_user_schedules:
            s_start = datetime.fromisoformat(s["start_date"]).date()
            s_end = datetime.fromisoformat(s["end_date"]).date()
            if s_start <= day_date <= s_end:
                count += 1
        weekly_counts.append({
            "day": day.strftime("%a")[0], # M, T, W, T, F, S, S
            "date": day.day,
            "count": count,
            "is_today": day_date == today.date()
        })
    pending_approvals = []
    if current_user["role"] == "SPV":
        # SPV only sees reports at "Pending SPV" stage where they are the current approver
        pending_approvals = await db.reports.find(
            {
                "current_approver": current_user["id"],
                "status": "Pending SPV"
            },
            {"_id": 0, "file_data": 0}
        ).to_list(100)
    elif current_user["role"] == "Manager":
        # Manager sees all reports at "Pending Manager" stage matching their Division/Region
        # 1. Division Mapping
        user_division = current_user.get("division")
        division_filter = [user_division]
        if user_division == "TS":
            division_filter.append("Apps")
        elif user_division == "Infra":
            division_filter.append("Fiberzone")
        # 2. Aggregation Pipeline
        pipeline = [
            {"$match": {"status": "Pending Manager"}},
            # Lookup submitter to get their division/region if needed
            {"$lookup": {
                "from": "users",
                "localField": "submitted_by",
                "foreignField": "id",
                "as": "submitter_info"
            }},
            {"$unwind": "$submitter_info"},
            # Determine Effective Region: Report.site_region > Submitter.region
            {"$addFields": {
                "effective_region": {
                    "$ifNull": ["$site_region", "$submitter_info.region"]
                },
                "submitter_division": "$submitter_info.division"
            }},
            # Filter by Division
            {"$match": {
                "submitter_division": {"$in": division_filter}
            }}
        ]
        # Filter by Region (if Manager has a region)
        # If Manager region is None/Global, they see all regions
        if current_user.get("region"):
             pipeline.append({
                 "$match": {"effective_region": current_user.get("region")}
             })
        # Projection to match original output format
        pipeline.append({
            "$project": {
                "_id": 0,
                "file_data": 0,
                "submitter_info": 0,
                "effective_region": 0,
                "submitter_division": 0
            }
        })
        pending_approvals = await db.reports.aggregate(pipeline).to_list(100)
    elif current_user["role"] == "VP":
        # VP sees ALL reports at "Pending VP" stage
        # VP has global view, no region/division restriction
        pending_approvals = await db.reports.find(
            {
                "status": "Pending VP"
            },
            {"_id": 0, "file_data": 0}
        ).to_list(100)
    open_tickets = []
    if current_user["role"] in ["Staff", "SPV", "Manager", "VP"]:
        query = {"status": {"$ne": "Closed"}}
        if current_user["role"] in ["Staff", "SPV", "Manager"]:
            query["assigned_to_division"] = current_user.get("division")
        open_tickets = await db.tickets.find(query, {"_id": 0}).to_list(100)
    # NEW: Add pending account approvals and shift change requests
    pending_accounts = []
    pending_shift_changes = []
    if current_user["role"] in ["Manager", "VP"]:
        query = {"account_status": "pending"}
        if current_user["role"] == "Manager":
            query["division"] = current_user.get("division")
            query["role"] = {"$ne": "Manager"}  # Consistency with get_pending_accounts
        elif current_user["role"] == "VP":
            query["role"] = "Manager"
        pending_accounts = await db.users.find(query, {"_id": 0, "password_hash": 0}).to_list(100)
        # Shift change requests
        query = {"status": "pending"}
        if current_user["role"] == "Manager":
            schedules = await db.schedules.find({"division": current_user.get("division")}, {"_id": 0}).to_list(10000)
            schedule_ids = [s["id"] for s in schedules]
            query["schedule_id"] = {"$in": schedule_ids}
        pending_shift_changes = await db.shift_change_requests.find(query, {"_id": 0}).to_list(100)
    # 4. Expiring Starlinks (NEW - Pop-up Notification trigger)
    # Trigger: H-3 days (3 days or less)
    expiring_starlinks = []
    # We include expired ones too (<= 3 days from now)
    now = datetime.now(timezone.utc)
    three_days_from_now = now + timedelta(days=3)
    starlinks_cursor = db.starlinks.find({
        "expiration_date": {
            "$lte": three_days_from_now.isoformat()
        }
    }, {"_id": 0})
    expiring_starlinks = await starlinks_cursor.to_list(length=100)
    return {
        "schedules_today": schedules_today,
        "pending_approvals": pending_approvals,
        "open_tickets": open_tickets,
        "pending_accounts": pending_accounts,
        "pending_shift_changes": pending_shift_changes,
        "expiring_starlinks": expiring_starlinks,
        "weekly_counts": weekly_counts
    }
