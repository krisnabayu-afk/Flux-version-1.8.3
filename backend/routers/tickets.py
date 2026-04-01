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

# ============ TICKET ENDPOINTS (V3) - UPDATED ============


@router.post("/tickets")
async def create_ticket(ticket_data: TicketCreate, current_user: dict = Depends(get_current_user)):
    # Get site name if site_id provided
    site_name = None
    site_region = None  # REGIONAL
    if ticket_data.site_id:
        site = await db.sites.find_one({"id": ticket_data.site_id}, {"_id": 0})
        if site:
            site_name = site["name"]
            site_region = site.get("region")  # REGIONAL
    ticket = Ticket(
        title=ticket_data.title,
        description=ticket_data.description,
        priority=ticket_data.priority,
        status="Open",
        assigned_to_division=ticket_data.assigned_to_division,
        created_by=current_user["id"],
        created_by_name=current_user["username"],
        site_id=ticket_data.site_id,
        site_name=site_name,
        site_region=site_region if ticket_data.site_id else None  # REGIONAL
    )
    doc = ticket.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    doc['updated_at'] = doc['updated_at'].isoformat()
    await db.tickets.insert_one(doc)
    manager = await db.users.find_one({"role": "Manager", "division": ticket_data.assigned_to_division}, {"_id": 0})
    if manager:
        await create_notification(
            user_id=manager["id"],
            title="New Ticket Assigned",
            message=f"New {ticket_data.priority} priority ticket: {ticket_data.title}",
            notification_type="ticket",
            related_id=ticket.id
        )
    return {"message": "Ticket created successfully", "id": ticket.id}


@router.get("/tickets", response_model=PaginatedTicketResponse)
async def get_tickets(
    page: int = 1,
    limit: int = 15,
    site_id: Optional[str] = None,
    region: Optional[str] = None,  # REGIONAL
    search: Optional[str] = None,  # NEW: Search parameter
    current_user: dict = Depends(get_current_user)
):
    # Universal visibility - all users can view all tickets
    pipeline = []
    # Match stage
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
            {"created_by_name": {"$regex": search, "$options": "i"}},
            {"site_name": {"$regex": search, "$options": "i"}}
        ]
    if match_stage:
        pipeline.append({"$match": match_stage})
    # Exclude _id
    pipeline.append({"$project": {"_id": 0}})
    # CUSTOM SORTING: Move Closed tickets to the bottom
    # 0 = Priority (Open, In Progress)
    # 1 = Closed
    pipeline.append({
        "$addFields": {
            "sort_priority": {
                "$cond": {
                    "if": {"$eq": ["$status", "Closed"]},
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
    result = await db.tickets.aggregate(pipeline).to_list(1)
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


@router.get("/tickets/list/all")
async def get_all_tickets_list(current_user: dict = Depends(get_current_user)):
    # Simple list of all tickets for dropdown selection
    tickets = await db.tickets.find({}, {"_id": 0, "id": 1, "title": 1, "created_at": 1}).to_list(1000)
    return tickets


@router.get("/tickets/{ticket_id}")
async def get_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


@router.patch("/tickets/{ticket_id}")
async def update_ticket(ticket_id: str, update_data: TicketUpdate, current_user: dict = Depends(get_current_user)):
    update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": update_dict}
    )
    return {"message": "Ticket updated successfully"}


@router.put("/tickets/{ticket_id}")
async def edit_ticket(ticket_id: str, edit_data: TicketUpdate, current_user: dict = Depends(get_current_user)):
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Prepare update data
    update_dict: dict[str, Any] = {}
    if edit_data.title:
        update_dict["title"] = edit_data.title
    if edit_data.description:
        update_dict["description"] = edit_data.description
    if edit_data.priority:
        update_dict["priority"] = edit_data.priority
    if edit_data.assigned_to_division:
        update_dict["assigned_to_division"] = edit_data.assigned_to_division
    if edit_data.site_id is not None:
        update_dict["site_id"] = edit_data.site_id
        # Get site name
        if edit_data.site_id:
            site = await db.sites.find_one({"id": edit_data.site_id}, {"_id": 0})
            if site:
                update_dict["site_name"] = site["name"]
        else:
            update_dict["site_name"] = None
    update_dict["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": update_dict}
    )
    return {"message": "Ticket edited successfully"}


@router.post("/tickets/{ticket_id}/close")
async def close_ticket(ticket_id: str, current_user: dict = Depends(get_current_user)):
    ticket = await db.tickets.find_one({"id": ticket_id}, {"_id": 0})
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if ticket.get("linked_report_id"):
        report = await db.reports.find_one({"id": ticket["linked_report_id"]}, {"_id": 0})
        if not report or report["status"] != "Final":
            raise HTTPException(status_code=400, detail="Cannot close ticket: linked report is not yet approved")
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {"status": "Closed", "updated_at": datetime.now(timezone.utc).isoformat()}}
    )
    return {"message": "Ticket closed successfully"}


@router.post("/tickets/{ticket_id}/comments")
async def add_ticket_comment(ticket_id: str, comment_data: TicketComment, current_user: dict = Depends(get_current_user)):
    comment = {
        "id": str(uuid.uuid4()),
        "user_id": current_user["id"],
        "user_name": current_user["username"],
        "comment": comment_data.comment,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$push": {"comments": comment}}
    )
    return {"message": "Comment added successfully"}


@router.post("/tickets/{ticket_id}/link-report/{report_id}")
async def link_report_to_ticket(ticket_id: str, report_id: str, current_user: dict = Depends(get_current_user)):
    await db.tickets.update_one(
        {"id": ticket_id},
        {"$set": {"linked_report_id": report_id}}
    )
    return {"message": "Report linked to ticket successfully"}
