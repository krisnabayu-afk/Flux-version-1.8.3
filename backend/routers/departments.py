from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from datetime import datetime, timezone
import uuid

from database import db
from utils import get_current_user
from models import Department, DepartmentCreate, DepartmentUpdate

router = APIRouter()

@router.get("/departments", response_model=List[Department])
async def get_departments():
    departments = await db.departments.find({}, {"_id": 0}).to_list(1000)
    return departments

@router.post("/departments", response_model=Department)
async def create_department(dept_data: DepartmentCreate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can manage departments")
    
    existing = await db.departments.find_one({"name": dept_data.name})
    if existing:
        raise HTTPException(status_code=400, detail="Department already exists")
        
    department = Department(
        name=dept_data.name,
        divisions=dept_data.divisions
    )
    doc = department.model_dump()
    doc['created_at'] = doc['created_at'].isoformat()
    
    await db.departments.insert_one(doc)
    return department

@router.put("/departments/{dept_id}", response_model=dict)
async def update_department(dept_id: str, dept_data: DepartmentUpdate, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can manage departments")
        
    existing = await db.departments.find_one({"id": dept_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Department not found")
        
    if dept_data.name and dept_data.name != existing["name"]:
        name_check = await db.departments.find_one({"name": dept_data.name})
        if name_check:
             raise HTTPException(status_code=400, detail="Department with this name already exists")
    
    update_dict = {k: v for k, v in dept_data.model_dump().items() if v is not None}
    
    if update_dict:
        await db.departments.update_one({"id": dept_id}, {"$set": update_dict})
        
    return {"message": "Department updated successfully"}

@router.delete("/departments/{dept_id}")
async def delete_department(dept_id: str, current_user: dict = Depends(get_current_user)):
    if current_user["role"] != "SuperUser":
        raise HTTPException(status_code=403, detail="Only SuperUser can manage departments")
        
    result = await db.departments.delete_one({"id": dept_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Department not found")
        
    return {"message": "Department deleted successfully"}
