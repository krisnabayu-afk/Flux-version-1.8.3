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

# ============ REPORT ENDPOINTS (V2) - UPDATED ============


@router.post("/reports")
async def create_report(
    title: str = Form(...),
    description: Optional[str] = Form(None),
    ticket_id: Optional[str] = Form(None),
    site_id: Optional[str] = Form(None),  # NEW
    category_id: Optional[str] = Form(None),  # NEW
    file: UploadFile = File(...),
    file_2: Optional[UploadFile] = File(None), # NEW: Second file
    current_user: dict = Depends(get_current_user)
):
    # Get site name if site_id provided for Folder Organization
    site_name = None
    site_region = None  # REGIONAL
    folder_name = "Unassigned"
    if site_id:
        site = await db.sites.find_one({"id": site_id}, {"_id": 0})
        if site:
            site_name = site["name"]
            site_region = site.get("region")  # REGIONAL
            # Sanitize folder name
            folder_name = "".join(c for c in site_name if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
    # Prepare file storage for report
    reports_dir = UPLOAD_DIR / "reports" / folder_name
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    file_extension = os.path.splitext(file.filename)[1]
    unique_filename = f"report_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
    file_path = reports_dir / unique_filename
    # Save file
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    file_url = f"/uploads/reports/{folder_name}/{unique_filename}"
    file_data = None # No longer storing base64 for new reports
    # Process second file if provided
    file_2_name = None
    file_2_url = None
    file_2_data = None
    if file_2:
        file_2_extension = os.path.splitext(file_2.filename)[1]
        unique_filename_2 = f"report_2_{timestamp}_{uuid.uuid4().hex[:8]}{file_2_extension}"
        file_path_2 = reports_dir / unique_filename_2
        with open(file_path_2, "wb") as buffer:
            shutil.copyfileobj(file_2.file, buffer)
        file_2_name = file_2.filename
        file_2_url = f"/uploads/reports/{folder_name}/{unique_filename_2}"
    # Get category name if category_id provided
    category_name = None
    if category_id:
        category = await db.activity_categories.find_one({"id": category_id}, {"_id": 0})
        if category:
            category_name = category["name"]
    # DETERMINING APPROVAL FLOW
    # Hierarchy: Staff -> SPV -> Manager -> VP -> Final
    # Department Mapping: Apps -> TS, Fiberzone -> Infra
    # Regional Lock: Approvers must be in same region as Creator/Site
    target_division = current_user.get("division")
    # Department Mapping
    if target_division == "Apps":
        target_division = "TS"
    elif target_division == "Fiberzone":
        target_division = "Infra"
    # Regional Lock - Use Site Region if available, else User Region
    target_region = site_region if site_region else current_user.get("region")
    status = "Pending Manager" # DEFAULT to Manager stage as per requirement
    current_approver = None
    # Logic based on Creator Role
    if current_user["role"] in ["Staff", "SPV"]:
        # Staff or SPV -> Needs Manager Approval
        status = "Pending Manager"
        # Division Mapping for search
        search_divisions = [target_division]
        original_division = current_user.get("division")
        if original_division and original_division not in search_divisions:
            search_divisions.append(original_division)
        # 1. Try to find Manager in same Division and Region
        query = {
            "role": "Manager", 
            "division": {"$in": search_divisions},
            "account_status": "approved"
        }
        if target_region:
             query["region"] = target_region
        manager = await db.users.find_one(query, {"_id": 0})
        # 2. Fallback: Try to find Manager in same Division without region (Global Manager)
        if not manager and target_region:
            del query["region"]
            query["region"] = {"$in": [None, "", "Global", "All Regions"]}
            manager = await db.users.find_one(query, {"_id": 0})
        # 3. Final Fallback: Any approved Manager in that division
        if not manager:
            if "region" in query: del query["region"]
            manager = await db.users.find_one(query, {"_id": 0})
        if not manager:
             error_msg = f"No Manager found for division {target_division}"
             if target_region:
                 error_msg += f" in region {target_region}"
             raise HTTPException(status_code=400, detail=error_msg + ". Please contact your administrator.")
        current_approver = manager["id"]
    elif current_user["role"] == "Manager":
        # Manager -> Needs VP Approval
        status = "Pending VP"
        # DEPARTMENT: Find VP in same department
        vp_query = {"role": "VP", "account_status": "approved"}
        if current_user.get("department"):
            vp_query["department"] = current_user.get("department")
        vp = await db.users.find_one(vp_query, {"_id": 0})
        if not vp:
            raise HTTPException(status_code=400, detail="No VP account found in your department to approve this report.")
        current_approver = vp["id"]
        # NOTE: Notification will be sent below to the VP
    elif current_user["role"] == "VP":
        # VP -> Auto Approved
        status = "Final"
        current_approver = None
    report = Report(
        category_id=category_id,
        category_name=category_name,
        title=title,
        description=description,
        file_name=file.filename,
        file_data=file_data,
        file_url=file_url, # NEW
        file_2_name=file_2_name,
        file_2_data=file_2_data,
        file_2_url=file_2_url,
        status=status,
        submitted_by=current_user["id"],
        submitted_by_name=current_user["username"],
        current_approver=current_approver,
        department=current_user.get("department"),  # DEPARTMENT: Denormalized
        ticket_id=ticket_id,
        site_id=site_id,
        site_name=site_name,
        site_region=site_region if site_id else None  # REGIONAL
    )
    doc = report.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.reports.insert_one(doc)
    if current_approver:
        await create_notification(
            user_id=current_approver,
            title="Report Need to Review",
            message=f"{current_user['username']} submitted: {title} - {site_name}",
            notification_type="report",
            related_id=report.id
        )
    return {"message": "Report submitted successfully", "id": report.id}


@router.get("/reports", response_model=PaginatedReportResponse)
async def get_reports(
    page: int = 1,
    limit: int = 15,
    site_id: Optional[str] = None, 
    division: Optional[str] = None,
    region: Optional[str] = None,  # REGIONAL
    search: Optional[str] = None,  # NEW: Search parameter
    mine: bool = Query(False),      # NEW: Filter for user's own reports
    approving: bool = Query(False), # NEW: Filter for reports pending user's approval
    current_user: dict = Depends(get_current_user),
):
    print(f"DEBUG: get_reports called with approving={approving}, user_role={current_user.get('role')}")
    # Universal visibility - all users can view all reports, but can filter
    # Start with aggregation pipeline
    pipeline = []
    # Match stage for site_id and region if provided
    match_stage = {}
    if site_id:
        match_stage["site_id"] = site_id
    # REGIONAL: Add region filter
    if region and region != 'all':
        match_stage["site_region"] = region
    # NEW: Add search filter
    if search:
        match_stage["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"submitted_by_name": {"$regex": search, "$options": "i"}},
            {"site_name": {"$regex": search, "$options": "i"}}
        ]
    # NEW: Filter for user's own reports
    if mine:
        match_stage["submitted_by"] = current_user["id"]
    # NEW: Filter for reports pending user's approval
    manager_approving_logic = False
    if approving:
        user_role = current_user.get("role", "").upper()
        if user_role == "VP":
            # VP sees reports in their department that are Pending VP
            match_stage["status"] = "Pending VP"
            if current_user.get("department"):
                match_stage["department"] = current_user["department"]
        elif user_role == "MANAGER":
            # Manager sees reports in their division/region/department that are Pending Manager or Pending SPV (Bypass)
            match_stage["status"] = {"$in": ["Pending SPV", "Pending Manager"]}
            if current_user.get("region"):
                # Strictly match same region
                match_stage["site_region"] = current_user["region"]
            # Strictly match same department if configured
            if current_user.get("department"):
                match_stage["department"] = current_user["department"]
            # Linear Division mapping flag
            manager_approving_logic = True
        elif user_role in ["SUPERUSER", "ADMIN"]:
            # Admin/SuperUser sees all reports that aren't Final, Revisi, or Draft (if any)
            match_stage["status"] = {"$in": ["Pending SPV", "Pending Manager", "Pending VP"]}
        else:
            # Fallback if role is unknown - still try to filter something if "approving" is true
            # This covers unexpected role names
            match_stage["status"] = {"$ne": "Final"}
            
    if match_stage:
        pipeline.append({"$match": match_stage})
    # User lookup for division filtering (either from dropdown or from Manager approval matching)
    needs_lookup = (division and division != "all") or manager_approving_logic
    if needs_lookup:
        # Lookup user info to check division
        pipeline.append({
            "$lookup": {
                "from": "users",
                "localField": "submitted_by",
                "foreignField": "id",
                "as": "submitter_info"
            }
        })
        # Unwind (preserve nulls just in case, though ideally shouldn't happen)
        pipeline.append({"$unwind": {"path": "$submitter_info", "preserveNullAndEmptyArrays": True}})
        # 1. Primary Filter based on division dropdown request
        if division and division != "all":
            if division == "Monitoring":
                pipeline.append({"$match": {"submitter_info.division": "Monitoring"}})
            elif division == "Infra & Fiberzone":
                pipeline.append({"$match": {"submitter_info.division": {"$in": ["Infra", "Fiberzone"]}}})
            elif division == "TS & Apps":
                pipeline.append({"$match": {"submitter_info.division": {"$in": ["TS", "Apps"]}}})
        # 2. Linear Stage Approval Division Matching
        if manager_approving_logic:
            # Map submitter division to match linear flow (Apps->TS, Fiberzone->Infra)
            pipeline.append({
                "$addFields": {
                    "mapped_submitter_div": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$submitter_info.division", "Apps"]}, "then": "TS"},
                                {"case": {"$eq": ["$submitter_info.division", "Fiberzone"]}, "then": "Infra"}
                            ],
                            "default": "$submitter_info.division"
                        }
                    }
                }
            })
            pipeline.append({"$match": {"mapped_submitter_div": current_user.get("division")}})
        # Cleanup - remove the joined info to keep response clean
        pipeline.append({"$project": {"submitter_info": 0, "mapped_submitter_div": 0}})
    # Exclude file_data and _id
    pipeline.append({"$project": {"file_data": 0, "_id": 0}})
    # CUSTOM SORTING: Prioritize Non-Final reports
    # 0 = Priority (Pending, Revision, Draft)
    # 1 = Final
    pipeline.append({
        "$addFields": {
            "sort_priority": {
                "$cond": {
                    "if": {"$eq": ["$status", "Final"]},
                    "then": 1,
                    "else": 0
                }
            }
        }
    })
    # Sort by priority (ascending) and then by created_at (descending)
    pipeline.append({
        "$sort": {
            "sort_priority": 1,
            "created_at": -1
        }
    })
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
    result = await db.reports.aggregate(pipeline).to_list(1)
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


@router.get("/reports/{report_id}")
async def get_report(report_id: str, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/reports/statistics/user-counts")
async def get_user_report_statistics(
    year: int,
    month: Optional[int] = None,
    category_id: Optional[str] = None,
    region: Optional[str] = None,  # NEW: Region filter
    view_type: str = "monthly",    # NEW: monthly or annual
    current_user: dict = Depends(get_current_user)
):
    # Calculate date range
    try:
        if view_type == "annual":
            start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            if not month:
                # Default to current month if not provided for monthly view, or error
                # Ideally frontend should provide it.
                raise ValueError("Month is required for monthly view")
            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid month or year")
    query = {
        "created_at": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    if category_id and category_id != "all":
        query["category_id"] = category_id
    # REGIONAL: Filter by region
    if region and region != 'all':
        query["site_region"] = region
    # Aggregate
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$submitted_by_name",
            "count": {"$sum": 1}
        }},
        {"$project": {
            "name": "$_id",
            "value": "$count",
            "_id": 0
        }}
    ]
    stats = await db.reports.aggregate(pipeline).to_list(None)
    return stats


@router.get("/reports/statistics/site-counts")
async def get_site_report_statistics(
    year: int,
    month: Optional[int] = None,
    category_id: Optional[str] = None,
    region: Optional[str] = None,  # NEW: Region filter
    view_type: str = "monthly",    # NEW: monthly or annual
    current_user: dict = Depends(get_current_user)
):
    # Calculate date range
    try:
        if view_type == "annual":
            start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            if not month:
                raise ValueError("Month is required for monthly view")
            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month or year")
    query = {
        "created_at": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    if category_id and category_id != "all":
        query["category_id"] = category_id
    # REGIONAL: Filter by region
    if region and region != 'all':
        query["site_region"] = region
    # Aggregate by site_name
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$site_name",
            "count": {"$sum": 1}
        }},
        {"$match": {"_id": {"$ne": None, "$ne": ""}}}, # Filter out reports without site name
        {"$project": {
            "name": "$_id",
            "value": "$count",
            "_id": 0
        }}
    ]
    stats = await db.reports.aggregate(pipeline).to_list(None)
    return stats


@router.get("/reports/statistics/category-counts")
async def get_category_report_statistics(
    year: int,
    month: Optional[int] = None,
    region: Optional[str] = None,
    view_type: str = "monthly",
    current_user: dict = Depends(get_current_user)
):
    # Calculate date range
    try:
        if view_type == "annual":
            start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            if not month:
                raise ValueError("Month is required for monthly view")
            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid month or year")
    query = {
        "created_at": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    # REGIONAL: Filter by region
    if region and region != 'all':
        query["site_region"] = region
    # Aggregate by category_name
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$category_name",
            "count": {"$sum": 1}
        }},
        {"$match": {"_id": {"$ne": None, "$ne": ""}}}, # Filter out reports without category name
        {"$project": {
            "name": "$_id",
            "value": "$count",
            "_id": 0
        }}
    ]
    stats = await db.reports.aggregate(pipeline).to_list(None)
    return stats
# NEW: Export Statistics CSV (Annual Data)


@router.get("/reports/statistics/export")
async def export_statistics_csv(
    year: int,
    region: Optional[str] = None,
    category_id: Optional[str] = None,
    dimension: str = "user", # 'user', 'site', or 'category'
    current_user: dict = Depends(get_current_user)
):
    # Reuse aggregation logic (force annual view)
    try:
        start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
        end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid year")
    query = {
        "created_at": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    if category_id and category_id != "all":
        query["category_id"] = category_id
    if region and region != 'all':
        query["site_region"] = region
    # Pipeline based on dimension
    if dimension == "user":
        group_id = "$submitted_by_name"
    elif dimension == "site":
        group_id = "$site_name"
    else: # category
        group_id = "$category_name"
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": group_id,
            "count": {"$sum": 1}
        }},
        {"$match": {"_id": {"$ne": None, "$ne": ""}}}, 
        {"$project": {
            "name": "$_id",
            "value": "$count",
            "_id": 0
        }}
    ]
    stats = await db.reports.aggregate(pipeline).to_list(None)
    # Generate CSV
    output = io.StringIO()
    writer = csv.writer(output)
    # Header
    if dimension == "user":
        header_name = "User Name"
    elif dimension == "site":
        header_name = "Site Name"
    else:
        header_name = "Category Name"
    writer.writerow([header_name, "Report Count"])
    # Rows
    for item in stats:
        writer.writerow([item["name"], item["value"]])
    return Response(content=output.getvalue(), media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=statistics_{year}_{dimension}.csv"
    })
# RATING: Leaderboard endpoint - ranks users by avg final_score on Final reports


@router.get("/reports/statistics/leaderboard")
async def get_rating_leaderboard(
    year: int,
    month: Optional[int] = None,
    view_type: str = "monthly",  # 'monthly' or 'annual'
    region: Optional[str] = None,
    department: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Returns a ranked leaderboard of users by their average final_score."""
    try:
        if view_type == "monthly" and month:
            start_date = datetime(year, month, 1, tzinfo=timezone.utc)
            if month == 12:
                end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
            else:
                end_date = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            start_date = datetime(year, 1, 1, tzinfo=timezone.utc)
            end_date = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date parameters")
    query = {
        "status": "Final",
        "final_score": {"$ne": None, "$exists": True},
        "updated_at": {
            "$gte": start_date.isoformat(),
            "$lte": end_date.isoformat()
        }
    }
    if region and region != "all":
        query["site_region"] = region
    if department and department != "all":
        query["department"] = department
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": "$submitted_by",
            "user_name": {"$first": "$submitted_by_name"},
            "avg_score": {"$avg": "$final_score"},
            "report_count": {"$sum": 1}
        }},
        {"$lookup": {
            "from": "users",
            "localField": "_id",
            "foreignField": "id",
            "as": "user_info"
        }},
        {"$project": {
            "user_id": "$_id",
            "user_name": 1,
            "avg_score": {"$round": ["$avg_score", 2]},
            "report_count": 1,
            "division": {"$arrayElemAt": ["$user_info.division", 0]},
            "region": {"$arrayElemAt": ["$user_info.region", 0]},
            "_id": 0
        }},
        {"$sort": {"avg_score": -1}}
    ]
    leaderboard = await db.reports.aggregate(pipeline).to_list(None)
    return leaderboard
# RATING: User performance endpoint - returns current user's monthly/yearly avg score


@router.get("/users/me/performance")
async def get_my_performance(
    year: int,
    month: int,
    current_user: dict = Depends(get_current_user)
):
    """Returns the authenticated user's monthly and yearly avg final_score."""
    user_id = current_user["id"]
    # Monthly range
    try:
        monthly_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            monthly_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            monthly_end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        yearly_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        yearly_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date parameters")
    base_query = {
        "submitted_by": user_id,
        "status": "Final",
        "final_score": {"$ne": None, "$exists": True}
    }
    # Monthly stats
    monthly_query = {**base_query, "updated_at": {"$gte": monthly_start.isoformat(), "$lte": monthly_end.isoformat()}}
    monthly_reports = await db.reports.find(monthly_query, {"_id": 0, "final_score": 1, "manager_notes": 1, "vp_notes": 1, "title": 1, "updated_at": 1}).to_list(None)
    monthly_scores = [r["final_score"] for r in monthly_reports if r.get("final_score") is not None]
    monthly_avg = round(sum(monthly_scores) / len(monthly_scores), 2) if monthly_scores else None
    # Yearly stats
    yearly_query = {**base_query, "updated_at": {"$gte": yearly_start.isoformat(), "$lte": yearly_end.isoformat()}}
    yearly_scores_raw = await db.reports.find(yearly_query, {"_id": 0, "final_score": 1}).to_list(None)
    yearly_scores = [r["final_score"] for r in yearly_scores_raw if r.get("final_score") is not None]
    yearly_avg = round(sum(yearly_scores) / len(yearly_scores), 2) if yearly_scores else None
    # Recent feedback (last 5 rated reports)
    recent_feedback_reports = await db.reports.find(
        {**base_query},
        {"_id": 0, "title": 1, "manager_rating": 1, "manager_notes": 1, "vp_rating": 1, "vp_notes": 1, "final_score": 1, "updated_at": 1}
    ).sort("updated_at", -1).limit(5).to_list(None)
    feedback = []
    for r in recent_feedback_reports:
        if r.get("manager_notes") or r.get("vp_notes"):
            feedback.append({
                "title": r.get("title"),
                "manager_rating": r.get("manager_rating"),
                "manager_notes": r.get("manager_notes"),
                "vp_rating": r.get("vp_rating"),
                "vp_notes": r.get("vp_notes"),
                "final_score": r.get("final_score"),
                "date": r.get("updated_at")
            })
    return {
        "monthly_avg": monthly_avg,
        "monthly_count": len(monthly_scores),
        "yearly_avg": yearly_avg,
        "yearly_count": len(yearly_scores),
        "recent_feedback": feedback
    }


@router.get("/users/{user_id}/performance")
async def get_user_performance(
    user_id: str,
    year: int,
    month: int,
    current_user: dict = Depends(get_current_user)
):
    """Returns a specific user's monthly and yearly avg final_score."""
    if current_user["id"] != user_id and current_user["role"] not in ["SuperUser", "VP", "Manager", "SPV"]:
        raise HTTPException(status_code=403, detail="Not authorized to view this user's performance")
    try:
        monthly_start = datetime(year, month, 1, tzinfo=timezone.utc)
        if month == 12:
            monthly_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        else:
            monthly_end = datetime(year, month + 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
        yearly_start = datetime(year, 1, 1, tzinfo=timezone.utc)
        yearly_end = datetime(year + 1, 1, 1, tzinfo=timezone.utc) - timedelta(microseconds=1)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date parameters")
    base_query = {
        "submitted_by": user_id,
        "status": "Final",
        "final_score": {"$ne": None, "$exists": True}
    }
    monthly_query = {**base_query, "updated_at": {"$gte": monthly_start.isoformat(), "$lte": monthly_end.isoformat()}}
    monthly_reports = await db.reports.find(monthly_query, {"_id": 0, "final_score": 1}).to_list(None)
    monthly_scores = [r["final_score"] for r in monthly_reports if r.get("final_score") is not None]
    monthly_avg = round(sum(monthly_scores) / len(monthly_scores), 2) if monthly_scores else None
    yearly_query = {**base_query, "updated_at": {"$gte": yearly_start.isoformat(), "$lte": yearly_end.isoformat()}}
    yearly_scores_raw = await db.reports.find(yearly_query, {"_id": 0, "final_score": 1}).to_list(None)
    yearly_scores = [r["final_score"] for r in yearly_scores_raw if r.get("final_score") is not None]
    yearly_avg = round(sum(yearly_scores) / len(yearly_scores), 2) if yearly_scores else None
    recent_feedback_reports = await db.reports.find(
        {**base_query},
        {"_id": 0, "title": 1, "manager_rating": 1, "manager_notes": 1, "vp_rating": 1, "vp_notes": 1, "final_score": 1, "updated_at": 1}
    ).sort("updated_at", -1).limit(5).to_list(None)
    feedback = []
    for r in recent_feedback_reports:
        if r.get("manager_notes") or r.get("vp_notes"):
            feedback.append({
                "title": r.get("title"),
                "manager_rating": r.get("manager_rating"),
                "manager_notes": r.get("manager_notes"),
                "vp_rating": r.get("vp_rating"),
                "vp_notes": r.get("vp_notes"),
                "final_score": r.get("final_score"),
                "date": r.get("updated_at")
            })
    return {
        "monthly_avg": monthly_avg,
        "monthly_count": len(monthly_scores),
        "yearly_avg": yearly_avg,
        "yearly_count": len(yearly_scores),
        "recent_feedback": feedback
    }


@router.post("/reports/approve")
async def approve_report(approval: ApprovalAction, current_user: dict = Depends(get_current_user)):
    # DEPARTMENT: Admin division cannot perform report approvals
    if current_user.get("division") == "Admin":
        raise HTTPException(status_code=403, detail="Users in Admin division cannot perform report approvals")
    report = await db.reports.find_one({"id": approval.report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    # NEW: Linear Workflow & Bypass Logic Implementation
    # 1. FETCH CONTEXT
    submitter = await db.users.find_one({"id": report["submitted_by"]}, {"_id": 0})
    site = await db.sites.find_one({"id": report.get("site_id")}, {"_id": 0})
    # Determine Report's Region (Site Region > Submitter Region)
    report_region = site.get("region") if site else submitter.get("region")
    # Determine Report's Division (Mapped)
    report_division = submitter.get("division")
    if report_division == "Apps": report_division = "TS"
    elif report_division == "Fiberzone": report_division = "Infra"
    # 2. AUTHORIZATION & REGIONAL LOCK CHECK
    is_authorized = False
    bypass_mode = None # "manager_bypass", "vp_override"
    # VP Override (no region check, but must match department)
    if current_user["role"] == "VP":
        # DEPARTMENT: VP can only approve reports from their own department
        report_department = report.get("department") or (submitter.get("department") if submitter else None)
        if current_user.get("department") and report_department and current_user.get("department") != report_department:
            pass  # Department mismatch - don't authorize
        else:
            is_authorized = True
            bypass_mode = "vp_override"
    # Manager Bypass or Normal Approval
    elif current_user["role"] == "Manager":
        # Must match Region
        if current_user.get("region") == report_region:
            # Must match Division
             if current_user.get("division") == report_division:
                 is_authorized = True
                 if report["status"] == "Pending SPV":
                     bypass_mode = "manager_bypass"
    # SPV Normal Approval
    elif current_user["role"] == "SPV":
        # Must match Region
        if current_user.get("region") == report_region:
            # Must match Division
             if current_user.get("division") == report_division:
                 # Must be the current approver stage
                 if report["status"] == "Pending SPV":
                     is_authorized = True
    # Check against specific assigned approver (Legacy/Backup check)
    if report.get("current_approver") == current_user["id"]:
        is_authorized = True
    if not is_authorized:
        raise HTTPException(status_code=403, detail="You are not authorized to approve this report (Region/Division mismatch).")
    if approval.action == "revisi":
        if not approval.comment:
            raise HTTPException(status_code=400, detail="Comment is required for revisi")
        await db.reports.update_one(
            {"id": approval.report_id},
            {
                "$set": {
                    "status": "Revisi",
                    "rejection_comment": approval.comment,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        await create_notification(
            user_id=report["submitted_by"],
            title="Report Needs Revision",
            message=f"Your report '{report['title']}' needs revision: {approval.comment}",
            notification_type="report",
            related_id=approval.report_id
        )
        return {"message": "Report sent for revision"}
    # RATING: Validate rating for Manager/VP approve actions
    if approval.action == "approve" and current_user["role"] in ["Manager", "VP"]:
        if approval.rating is not None and not (1 <= approval.rating <= 5):
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
    # 3. DETERMINE NEXT STATUS (SEQUENTIAL STAGE-BASED)
    new_status = report["status"]
    new_approver = None
    # Logic based on NEXT stage
    if report["status"] == "Pending SPV":
        # SPV stage approved -> Move to Manager
        new_status = "Pending Manager"
        # Division Mapping for search
        search_divisions = [report_division]
        if report_division == "Apps" and "TS" not in search_divisions: search_divisions.append("TS")
        if report_division == "Fiberzone" and "Infra" not in search_divisions: search_divisions.append("Infra")
        # 1. Try to find Manager in same Division and Region
        query = {
            "role": "Manager", 
            "division": {"$in": search_divisions},
            "region": report_region,
            "account_status": "approved"
        }
        managers = await db.users.find(query, {"_id": 0}).to_list(None)
        # 2. Fallback: Global Manager
        if not managers:
            query["region"] = {"$in": [None, "", "Global", "All Regions"]}
            managers = await db.users.find(query, {"_id": 0}).to_list(None)
        # 3. Final Fallback: Any manager in division
        if not managers:
            del query["region"]
            managers = await db.users.find(query, {"_id": 0}).to_list(None)
        if managers:
            # Set the first manager as the primary "current_approver" for tracking
            new_approver = managers[0]["id"]
            # Send notification to ALL found managers
            for mgr in managers:
                 await create_notification(
                    user_id=mgr["id"],
                    title="Ada Report Baru, Tolong take Action!",
                    message=f"Report '{report['title']}' is awaiting your action",
                    notification_type="report",
                    related_id=approval.report_id
                )
        else:
            raise HTTPException(status_code=400, detail=f"Cannot proceed: No Manager found for {report_division} in {report_region}")
    elif report["status"] == "Pending Manager":
        # Manager approves -> Move to Pending VP
        new_status = "Pending VP"
        # DEPARTMENT: Find VPs in the same department as the report
        vp_query = {"role": "VP", "account_status": "approved"}
        report_dept = report.get("department") or (submitter.get("department") if submitter else None)
        if report_dept:
            vp_query["department"] = report_dept
        vps = await db.users.find(vp_query, {"_id": 0}).to_list(None)
        if vps:
            # Set the first VP as the primary "current_approver"
            new_approver = vps[0]["id"]
            # Send notification to ALL VPs
            for vp in vps:
                await create_notification(
                    user_id=vp["id"],
                    title="Report Needs Action",
                    message=f"Report '{report['title']}' is awaiting your action",
                    notification_type="report",
                    related_id=approval.report_id
                )
    elif report["status"] == "Pending VP":
        new_status = "Final"
        new_approver = None
    # OVERRIDE: If VP is the one approving, it always goes to Final regardless of stage
    if current_user["role"] == "VP":
        new_status = "Final"
        new_approver = None
    # RATING: Build rating update fields
    rating_update: dict[str, Any] = {}
    if approval.action == "approve" and current_user["role"] in ["Manager", "VP"] and approval.rating is not None:
        if current_user["role"] == "Manager":
            rating_update["manager_rating"] = approval.rating
            rating_update["manager_notes"] = approval.notes or ""
        elif current_user["role"] == "VP":
            rating_update["vp_rating"] = approval.rating
            rating_update["vp_notes"] = approval.notes or ""
    # RATING: Compute final_score if we are moving to Final
    if new_status == "Final":
        # Get the freshest rating values (merging existing + new)
        manager_rating = rating_update.get("manager_rating", report.get("manager_rating"))
        vp_rating = rating_update.get("vp_rating", report.get("vp_rating"))
        if manager_rating is not None and vp_rating is not None:
            rating_update["final_score"] = (manager_rating + vp_rating) / 2
        elif vp_rating is not None:
            # VP bypassed Manager - use VP rating only
            rating_update["final_score"] = float(vp_rating)
        elif manager_rating is not None:
            # Only manager rated (edge case)
            rating_update["final_score"] = float(manager_rating)
    # AUDIT TRAIL
    audit_message = f"Approved by {current_user['username']} ({current_user['role']})"
    if bypass_mode == "manager_bypass":
        audit_message += " (Manager Approved)"
    elif bypass_mode == "vp_override":
        audit_message += " (VP Approved)"
    if approval.rating is not None and current_user["role"] in ["Manager", "VP"]:
        audit_message += f" — Rating: {approval.rating}/5"
    audit_comment = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "user_name": "System",
        "text": audit_message,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    update_fields = {
        "status": new_status,
        "current_approver": new_approver,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **rating_update
    }
    await db.reports.update_one(
        {"id": approval.report_id},
        {
            "$set": update_fields,
            "$push": {"comments": audit_comment}
        }
    )
    if new_status == "Final":
        await create_notification(
            user_id=report["submitted_by"],
            title="Report Approved",
            message=f"Your report '{report['title']}' has been fully approved! Tolong diupload ke notes",
            notification_type="report",
            related_id=approval.report_id
        )
    elif new_approver:
        # Notifications already sent in the logic above for multiple recipients
        pass
    return {"message": "Report approved", "new_status": new_status}


@router.post("/reports/cancel-approval")
async def cancel_report_approval(request: CancelApprovalRequest, current_user: dict = Depends(get_current_user)):
    """
    Cancel a previous approval and revert the report to the previous pending status.
    Only VP and Manager can cancel approvals.
    """
    # DEPARTMENT: Admin division cannot perform report approvals
    if current_user.get("division") == "Admin":
        raise HTTPException(status_code=403, detail="Users in Admin division cannot perform report actions")
    report = await db.reports.find_one({"id": request.report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    current_status = report["status"]
    # Cannot cancel if report is in initial pending state or revision
    if current_status in ["Pending SPV", "Pending Manager", "Revisi"]:
        raise HTTPException(status_code=400, detail="Cannot cancel approval at this stage")
    # Fetch context for authorization
    submitter = await db.users.find_one({"id": report["submitted_by"]}, {"_id": 0})
    site = await db.sites.find_one({"id": report.get("site_id")}, {"_id": 0})
    # Determine Report's Region and Division
    report_region = "all"
    if site and site.get("region"):
        report_region = site.get("region")
    elif submitter and submitter.get("region"):
        report_region = submitter.get("region")
    report_division = "all"
    if submitter and submitter.get("division"):
        report_division = submitter.get("division")
        if report_division == "Apps": report_division = "TS"
        elif report_division == "Fiberzone": report_division = "Infra"
    # Authorization check
    is_authorized = False
    if current_user["role"] == "VP":
        # VP can cancel any approval
        is_authorized = True
    elif current_user["role"] == "Manager":
        # Manager can cancel if region and division match
        if current_user.get("region") == report_region and current_user.get("division") == report_division:
            # Can only cancel Pending VP or Final (not their own pending state)
            if current_status in ["Pending VP", "Final"]:
                is_authorized = True
    if not is_authorized:
        raise HTTPException(status_code=403, detail="You are not authorized to cancel this approval")
    # Determine previous status and approver
    new_status = None
    new_approver = None
    if current_status == "Final":
        # Revert to Pending VP
        new_status = "Pending VP"
        # DEPARTMENT: Find VP in same department as the report
        vp_query = {"role": "VP", "account_status": "approved"}
        report_dept = report.get("department")
        if report_dept:
            vp_query["department"] = report_dept
        vp = await db.users.find_one(vp_query, {"_id": 0})
        if vp:
            new_approver = vp["id"]
    elif current_status == "Pending VP":
        # Revert to Pending Manager
        new_status = "Pending Manager"
        # Find Manager (Same Region, Same Division)
        manager = await db.users.find_one({
            "role": "Manager",
            "division": report_division,
            "region": report_region,
            "account_status": "approved"
        }, {"_id": 0})
        if manager:
            new_approver = manager["id"]
        else:
            raise HTTPException(status_code=400, detail=f"Cannot revert: No Manager found for {report_division} in {report_region}")
    # Create audit trail comment
    audit_comment = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "user_name": "System",
        "text": f"System Audit: Approval cancelled by {current_user['role']} {current_user['username']}. Status reverted from {current_status} to {new_status}",
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    # Update report
    await db.reports.update_one(
        {"id": request.report_id},
        {
            "$set": {
                "status": new_status,
                "current_approver": new_approver,
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {"comments": audit_comment}
        }
    )
    # Notify the new approver
    if new_approver:
        await create_notification(
            user_id=new_approver,
            title="Report Approval Cancelled - Action Required",
            message=f"Report '{report['title']}' approval was cancelled and is now awaiting your review",
            notification_type="report",
            related_id=request.report_id
        )
    return {"message": "Approval cancelled successfully", "new_status": new_status}


@router.put("/reports/{report_id}")
async def edit_report(
    report_id: str, 
    title: str = Form(None),
    description: str = Form(None),
    site_id: str = Form(None),
    ticket_id: str = Form(None),
    file: Optional[UploadFile] = File(None),
    file_2: Optional[UploadFile] = File(None),
    current_user: dict = Depends(get_current_user)
):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    # Only the creator can edit their report
    if report["submitted_by"] != current_user["id"]:
        raise HTTPException(status_code=403, detail="You can only edit your own reports")
    # Prepare update data
    update_dict: dict[str, Any] = {}
    if title:
        update_dict["title"] = title
    if description:
        update_dict["description"] = description
    if site_id is not None:
        update_dict["site_id"] = site_id if site_id != "" else None
        # Get site name
        if update_dict["site_id"]:
            site = await db.sites.find_one({"id": update_dict["site_id"]}, {"_id": 0})
            if site:
                update_dict["site_name"] = site["name"]
        else:
            update_dict["site_name"] = None
    if ticket_id is not None:
        update_dict["ticket_id"] = ticket_id if ticket_id != "" else None
    # Handle file update
    if file:
        # Determine folder name (use current site or new site if changed)
        # Note: ticket_id/site_id/title/desc might be updated above independently
        # We need the EFFECTIVE site_id for the file organization
        effective_site_id = site_id if site_id is not None else report.get("site_id")
        folder_name = "Unassigned"
        if effective_site_id:
             # If site_id came from form (site_id is not None), we might need to fetch it
             # If it came from DB record, we might need to fetch it too properly
             site = await db.sites.find_one({"id": effective_site_id}, {"_id": 0})
             if site:
                 folder_name = "".join(c for c in site["name"] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        # Prepare file storage for report
        reports_dir = UPLOAD_DIR / "reports" / folder_name
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_extension = os.path.splitext(file.filename)[1]
        unique_filename = f"report_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = reports_dir / unique_filename
        # Save file
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        update_dict["file_name"] = file.filename
        update_dict["file_url"] = f"/uploads/reports/{folder_name}/{unique_filename}"
        update_dict["file_data"] = None # Clear old data if exists
    # Handle second file update
    if file_2:
        # Determine folder name (use current site or new site if changed)
        effective_site_id = site_id if site_id is not None else report.get("site_id")
        folder_name = "Unassigned"
        if effective_site_id:
             site = await db.sites.find_one({"id": effective_site_id}, {"_id": 0})
             if site:
                 folder_name = "".join(c for c in site["name"] if c.isalnum() or c in (' ', '-', '_')).strip().replace(' ', '_')
        reports_dir = UPLOAD_DIR / "reports" / folder_name
        reports_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        file_extension = os.path.splitext(file_2.filename)[1]
        unique_filename = f"report_2_{timestamp}_{uuid.uuid4().hex[:8]}{file_extension}"
        file_path = reports_dir / unique_filename
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file_2.file, buffer)
        update_dict["file_2_name"] = file_2.filename
        update_dict["file_2_url"] = f"/uploads/reports/{folder_name}/{unique_filename}"
        update_dict["file_2_data"] = None
    # NEW: If status is 'Revisi', reset to start of approval flow
    if report["status"] == "Revisi":
        # RE-EVALUATE APPROVAL FLOW (Exact copy of create_report logic)
        # 1. Fetch Context
        report_creator = await db.users.find_one({"id": report["submitted_by"]}, {"_id": 0})
        if not report_creator:
            raise HTTPException(status_code=404, detail="Report creator not found")
        # Determine Effectve Site ID (Updated or Original)
        # Note: update_dict has the NEW site_id if it was changed in this same request
        effective_site_id = update_dict.get("site_id", report.get("site_id"))
        effective_site_region = None
        if effective_site_id:
             s = await db.sites.find_one({"id": effective_site_id}, {"_id": 0})
             if s: effective_site_region = s.get("region")
        # Determine target region
        target_region = effective_site_region if effective_site_region else report_creator.get("region")
        # Division Mapping for search (Apps -> TS, Fiberzone -> Infra)
        target_division = report_creator.get("division")
        if target_division == "Apps": target_division = "TS"
        elif target_division == "Fiberzone": target_division = "Infra"
        status = "Pending SPV"
        first_approver = None
        # Logic based on Creator Role
        if report_creator["role"] in ["Staff", "SPV"]:
             status = "Pending Manager"
             query = {"role": "Manager", "division": target_division, "account_status": "approved"}
             if target_region: query["region"] = target_region
             managers = await db.users.find(query, {"_id": 0}).to_list(None)
             if not managers:
                 error_msg = f"No Manager found for division {target_division}"
                 if target_region: error_msg += f" in region {target_region}"
                 raise HTTPException(status_code=400, detail=error_msg)
             first_approver = managers[0]["id"]
        elif report_creator["role"] == "Manager":
             status = "Pending VP"
             current_approver_role = "VP"
             # DEPARTMENT: Find VP in same department as the report creator
             vp_query = {"role": "VP", "account_status": "approved"}
             creator_dept = report_creator.get("department")
             if creator_dept:
                 vp_query["department"] = creator_dept
             vps = await db.users.find(vp_query, {"_id": 0}).to_list(None)
             if not vps:
                 raise HTTPException(status_code=400, detail="No VP found in your department")
             first_approver = vps[0]["id"]
        elif report_creator["role"] == "VP":
             status = "Final"
             current_approver_role = None
             first_approver = None
        if status != "Final":
            update_dict["status"] = status
            update_dict["current_approver"] = first_approver
            update_dict["rejection_comment"] = None 
            # Notify the new approver(s)
            if first_approver:
                recipients = []
                if status == "Pending Manager":
                     # Re-fetch all managers that match the query used above
                     recipients = await db.users.find(query, {"_id": 0}).to_list(None)
                elif status == "Pending VP":
                     # Re-fetch all VPs
                     recipients = await db.users.find({"role": "VP", "account_status": "approved"}, {"_id": 0}).to_list(None)
                if recipients:
                    for recipient in recipients:
                        await create_notification(
                            user_id=recipient["id"],
                            title="Resubmitted Report Needs Approval",
                            message=f"Resubmitted report '{update_dict.get('title', report['title'])}' is awaiting your approval",
                            notification_type="report",
                            related_id=report["id"]
                        )
        else:
             update_dict["status"] = "Final"
             update_dict["current_approver"] = None
             update_dict["rejection_comment"] = None
    # AUDIT TRAIL for revision
    revision_doc = {
        "id": str(uuid.uuid4()),
        "report_id": report_id,
        "version": report["version"],
        "title": report["title"],
        "description": report.get("description"),
        "file_name": report.get("file_name"),
        "file_url": report.get("file_url"),
        "file_data": report.get("file_data"),
        "file_2_name": report.get("file_2_name"),
        "file_2_url": report.get("file_2_url"),
        "file_2_data": report.get("file_2_data"),
        "updated_at": report.get("updated_at") or report.get("created_at")
    }
    await db.report_revisions.insert_one(revision_doc)
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    update_dict["version"] = report["version"] + 1
    await db.reports.update_one(
        {"id": report_id},
        {"$set": update_dict}
    )
    return {"message": "Report updated successfully"}


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    if report["submitted_by"] != current_user["id"] and current_user["role"] not in ["Manager", "VP"]:
        raise HTTPException(status_code=403, detail="Not authorized to delete this report")
    # Unlink from ticket if linked
    if report.get("ticket_id"):
        await db.tickets.update_one(
            {"id": report["ticket_id"]},
            {"$unset": {"linked_report_id": ""}}
        )
    # Also search by linked_report_id just in case
    await db.tickets.update_many(
        {"linked_report_id": report_id},
        {"$unset": {"linked_report_id": ""}}
    )
    await db.reports.delete_one({"id": report_id})
    # Also delete revisions
    await db.report_revisions.delete_many({"report_id": report_id})
    return {"message": "Report deleted successfully"}


@router.get("/reports/{report_id}/revisions")
async def get_report_revisions(report_id: str, current_user: dict = Depends(get_current_user)):
    # Check if report exists
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    revisions = await db.report_revisions.find({"report_id": report_id}, {"_id": 0}).sort("version", -1).to_list(100)
    return revisions


@router.get("/reports/{report_id}/revisions/{version}")
async def get_report_revision_detail(report_id: str, version: int, current_user: dict = Depends(get_current_user)):
    revision = await db.report_revisions.find_one({"report_id": report_id, "version": version}, {"_id": 0})
    if not revision:
        raise HTTPException(status_code=404, detail="Revision not found")
    return revision


@router.post("/reports/{report_id}/comments")
async def add_report_comment(report_id: str, comment_data: CommentCreate, current_user: dict = Depends(get_current_user)):
    report = await db.reports.find_one({"id": report_id}, {"_id": 0})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    comment = Comment(
        user_id=current_user["id"],
        user_name=current_user["username"],
        text=comment_data.text
    )
    comment_doc = comment.model_dump()
    comment_doc['created_at'] = comment_doc['created_at'].isoformat()
    await db.reports.update_one(
        {"id": report_id},
        {"$push": {"comments": comment_doc}}
    )
    # Notify report creator if someone else comments
    if report["submitted_by"] != current_user["id"]:
        await create_notification(
            user_id=report["submitted_by"],
            title="New Comment on Report",
            message=f"{current_user['username']} commented on '{report['title']}'",
            notification_type="report",
            related_id=report_id
        )
    return {"message": "Comment added successfully"}
