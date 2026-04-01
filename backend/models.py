from pydantic import BaseModel, ConfigDict, Field
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone
import uuid

class User(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    username: str
    email: str
    password_hash: str
    role: str
    department: Optional[str] = None  # DEPARTMENT: e.g. "Technical Operation"
    division: Optional[str] = None
    region: Optional[str] = None  # REGIONAL: Region 1, Region 2, Region 3
    account_status: str = "pending"  # NEW: pending, approved, rejected
    profile_photo: Optional[str] = None  # NEW: Base64 encoded photo
    telegram_id: Optional[str] = None  # NEW: Telegram Chat ID
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class UserCreate(BaseModel):
    username: str
    email: str
    password: str
    role: str
    department: Optional[str] = None  # DEPARTMENT: e.g. "Technical Operation"
    division: Optional[str] = None
    region: Optional[str] = None  # REGIONAL: Required for non-VP roles


class UserLogin(BaseModel):
    email: str
    password: str


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    department: Optional[str] = None  # DEPARTMENT
    division: Optional[str] = None
    region: Optional[str] = None  # REGIONAL
    account_status: Optional[str] = None
    profile_photo: Optional[str] = None
    telegram_id: Optional[str] = None


class UserProfileUpdate(BaseModel):  # NEW
    username: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None
    confirm_password: Optional[str] = None
    telegram_id: Optional[str] = None


class UserUpdateAdmin(BaseModel):  # NEW: Admin update model
    role: Optional[str] = None
    department: Optional[str] = None  # DEPARTMENT
    division: Optional[str] = None
    region: Optional[str] = None
    account_status: Optional[str] = None


class AccountApprovalAction(BaseModel):  # NEW
    user_id: str
    action: str  # approve or reject


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse
# NEW: Site Model
class Site(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    cid: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    region: Optional[str] = None  # REGIONAL: Region 1, Region 2, Region 3
    status: str = "active"  # active, inactive
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class SiteCreate(BaseModel):
    name: str
    cid: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    region: Optional[str] = None  # REGIONAL
class SiteUpdate(BaseModel):
    name: Optional[str] = None
    cid: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    region: Optional[str] = None  # REGIONAL
    status: Optional[str] = None
# NEW: Activity Category Model
class ActivityCategory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class CategoryCreate(BaseModel):
    name: str
class Schedule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    division: str
    category_id: Optional[str] = None  # NEW: Activity category
    category_name: Optional[str] = None  # NEW: Activity category name
    title: str
    description: Optional[str] = None
    start_date: datetime
    end_date: Optional[datetime] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ticket_id: Optional[str] = None
    site_id: Optional[str] = None  # NEW
    site_name: Optional[str] = None  # NEW
    site_region: Optional[str] = None  # REGIONAL: Denormalized for filtering
    # NOTIFICATION FLAGS: Prevent duplicate notifications
    notified_1h_before_start: bool = False
    notified_30m_before_end: bool = False
    auto_finished: bool = False
class ScheduleCreate(BaseModel):
    user_ids: List[str]  # Changed from user_id to user_ids for bulk assignment
    division: Optional[str] = None # Made optional for bulk assignment
    category_id: Optional[str] = None  # NEW: Activity category
    title: str
    description: Optional[str] = None
    start_date: str
    end_date: Optional[str] = None
    ticket_id: Optional[str] = None
    site_id: str  # Required
class ScheduleUpdate(BaseModel):
    user_id: Optional[str] = None
    user_name: Optional[str] = None
    category_id: Optional[str] = None  # NEW: Activity category
    title: Optional[str] = None
    description: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    site_id: Optional[str] = None  # NEW
# NEW: Activity Models
class Activity(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schedule_id: str
    user_id: str
    user_name: str
    division: str
    action_type: str  # start, finish, cancel, hold
    status: str  # In Progress, Finished, Cancelled, On Hold
    notes: Optional[str] = None
    reason: Optional[str] = None  # Required for cancel
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    progress_updates: List[dict] = []  # NEW: Array of timestamped progress updates
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class ActivityCreate(BaseModel):
    schedule_id: str
    action_type: str  # start, finish, cancel, hold
    notes: Optional[str] = None
    reason: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None  # Required when action_type is cancel
class ActivityProgressUpdate(BaseModel):
    activity_id: str
    update_text: str  # The progress update/comment
class AutoPushUpdateQuery(BaseModel):
    activity_id: str
    latitude: Optional[float] = None
    longitude: Optional[float] = None
# NEW: Shift Change Request
class ShiftChangeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schedule_id: str
    requested_by: str
    requested_by_name: str
    reason: str
    new_start_date: datetime
    new_end_date: datetime
    status: str = "pending"  # pending, approved, rejected
    reviewed_by: Optional[str] = None
    review_comment: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class ShiftChangeRequestCreate(BaseModel):
    schedule_id: str
    reason: str
    new_start_date: str
    new_end_date: str
class ShiftChangeReviewAction(BaseModel):
    request_id: str
    action: str  # approve or reject
    comment: Optional[str] = None
class CommentCreate(BaseModel):
    text: str
class Comment(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    text: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class Report(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    category_id: Optional[str] = None  # NEW: Activity category
    category_name: Optional[str] = None  # NEW: Activity category name
    title: str
    description: Optional[str] = None
    file_name: str
    file_data: Optional[str] = None
    file_url: Optional[str] = None # NEW
    file_2_name: Optional[str] = None # NEW: Second file
    file_2_data: Optional[str] = None
    file_2_url: Optional[str] = None
    status: str
    submitted_by: str
    submitted_by_name: str
    current_approver: Optional[str] = None
    department: Optional[str] = None  # DEPARTMENT: Denormalized from submitter
    ticket_id: Optional[str] = None
    site_id: Optional[str] = None  # NEW
    site_name: Optional[str] = None  # NEW
    site_region: Optional[str] = None  # REGIONAL: Denormalized for filtering
    version: int = 1
    rejection_comment: Optional[str] = None
    comments: List[Comment] = []
    # RATING: Performance scoring fields
    manager_rating: Optional[int] = None   # 1-5 stars from Manager
    manager_notes: Optional[str] = None    # Feedback from Manager
    vp_rating: Optional[int] = None        # 1-5 stars from VP
    vp_notes: Optional[str] = None         # Feedback from VP
    final_score: Optional[float] = None    # Average of manager + vp ratings
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class ApprovalAction(BaseModel):
    report_id: str
    action: str
    comment: Optional[str] = None
    rating: Optional[int] = None   # 1-5 stars (required for approve action by Manager/VP)
    notes: Optional[str] = None    # Optional feedback from approver
class CancelApprovalRequest(BaseModel):
    report_id: str
class ReportUpdate(BaseModel):
    category_id: Optional[str] = None  # NEW: Activity category
    title: Optional[str] = None
    description: Optional[str] = None
    site_id: Optional[str] = None
    ticket_id: Optional[str] = None
class PaginatedReportResponse(BaseModel):
    items: List[Report]
    total: int
    page: int
    limit: int
    total_pages: int
class PaginatedSiteResponse(BaseModel):
    items: List[Site]
    total: int
    page: int
    limit: int
    total_pages: int
class Ticket(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    title: str
    description: str
    priority: str
    status: str
    assigned_to_division: str
    assigned_to: Optional[str] = None
    created_by: str
    created_by_name: str
    linked_report_id: Optional[str] = None
    site_id: Optional[str] = None  # NEW
    site_name: Optional[str] = None  # NEW
    site_region: Optional[str] = None  # REGIONAL: Denormalized for filtering
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    comments: List[dict] = []
class PaginatedTicketResponse(BaseModel):
    items: List[Ticket]
    total: int
    page: int
    limit: int
    total_pages: int
class TicketCreate(BaseModel):
    title: str
    description: str
    priority: str
    assigned_to_division: str
    site_id: Optional[str] = None
class TicketUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    priority: Optional[str] = None
    status: Optional[str] = None
    assigned_to_division: Optional[str] = None
    assigned_to: Optional[str] = None
    site_id: Optional[str] = None
class TicketComment(BaseModel):
    ticket_id: str
    comment: str
class Notification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    message: str
    type: str
    related_id: Optional[str] = None
    read: bool = False
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class Holiday(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    description: str
    is_recurring: bool = False
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class HolidayCreate(BaseModel):
    start_date: str
    end_date: Optional[str] = None
    description: str
    is_recurring: bool = False
class VersionUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version: str  # e.g., "Flux Version 1.1"
    changes: List[str]  # e.g., ["add schedule"]
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class VersionUpdateCreate(BaseModel):
    version: str
    changes: List[str]
# ============ FEEDBACK MODELS ============
class Feedback(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    user_name: str
    user_role: str
    title: str
    description: str
    status: str = "Open"  # Open or Closed
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class FeedbackCreate(BaseModel):
    title: str
    description: str
class FeedbackStatusUpdate(BaseModel):
    status: str  # Open or Closed
class FeedbackComment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    feedback_id: str
    user_id: str
    user_name: str
    user_role: str
    content: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class FeedbackCommentCreate(BaseModel):
    content: str
# ============ CERTIFICATION MODELS ============
class UserCertification(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_id: str
    title: str
    date_taken: str  # YYYY-MM-DD
    description: Optional[str] = None
    pdf_path: Optional[str] = None
    pdf_name: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class UserCertificationCreate(BaseModel):
    title: str
    date_taken: str
    description: Optional[str] = None
# ============ HELPER FUNCTIONS ============
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    sn: str
    position: str # Location/Site
    account_email: str
    package_status: str # Linked Account & Current Package Name
    expiration_date: datetime
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
class StarlinkCreate(BaseModel):
    name: str
    sn: str
    position: str
    account_email: str
    package_status: str
    expiration_date: str # Expecting ISO string or YYYY-MM-DD
class StarlinkUpdate(BaseModel):
    name: Optional[str] = None
    sn: Optional[str] = None
    position: Optional[str] = None
    account_email: Optional[str] = None
    package_status: Optional[str] = None
    expiration_date: Optional[str] = None
