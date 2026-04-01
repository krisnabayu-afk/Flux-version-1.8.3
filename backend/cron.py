import asyncio
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
import uuid

from database import db
from utils import MONITORING_SHIFTS, send_telegram_message, create_notification
import logging

logger = logging.getLogger(__name__)

# ============ SCHEDULE NOTIFICATION CRON JOB ============
# UTC+8 timezone for local time comparisons
LOCAL_TZ = timezone(timedelta(hours=8))
async def schedule_notification_cron_job():
    """Background job that runs every minute to check for upcoming/ending activities."""
    try:
        now = datetime.now(LOCAL_TZ)
        logging.info(f"[CRON] Schedule notification check at {now.isoformat()}")
        # ---- 1. Notify 1 hour before start ----
        window_start_55 = now + timedelta(minutes=55)
        window_start_65 = now + timedelta(minutes=65)
        schedules_starting = await db.schedules.find({
            "notified_1h_before_start": {"$ne": True},
            "start_date": {
                "$gte": window_start_55.isoformat(),
                "$lte": window_start_65.isoformat()
            }
        }, {"_id": 0}).to_list(500)
        for schedule in schedules_starting:
            site_name = schedule.get("site_name", "Unknown")
            title = schedule.get("title", "")
            user_id = schedule["user_id"]
            notif_message = f"Ada jadwal mendatang *{title}* di *{site_name}* dalam 1 jam mendatang. Jangan lupa bersiap!"
            await create_notification(
                user_id=user_id,
                title="⏰ Jadwal Mendatang",
                message=notif_message,
                notification_type="schedule_reminder",
                related_id=schedule["id"]
            )
            await db.schedules.update_one(
                {"id": schedule["id"]},
                {"$set": {"notified_1h_before_start": True}}
            )
            logging.info(f"[CRON] Sent 1h-before-start notification for schedule {schedule['id']} to user {user_id}")
        # ---- 2. Notify 30 minutes before end ----
        window_end_25 = now + timedelta(minutes=25)
        window_end_35 = now + timedelta(minutes=35)
        schedules_ending = await db.schedules.find({
            "notified_30m_before_end": {"$ne": True},
            "end_date": {
                "$gte": window_end_25.isoformat(),
                "$lte": window_end_35.isoformat()
            }
        }, {"_id": 0}).to_list(500)
        for schedule in schedules_ending:
            site_name = schedule.get("site_name", "Unknown")
            end_date_str = schedule.get("end_date", "")
            user_id = schedule["user_id"]
            # Format end time for display
            try:
                end_dt = datetime.fromisoformat(end_date_str)
                end_time_display = end_dt.strftime("%H:%M")
            except (ValueError, TypeError):
                end_time_display = end_date_str
            notif_message = f"30 menit lagi aktivitas di *{site_name}* akan berakhir. Sistem akan melakukan finish secara otomatis pada jam *{end_time_display}*."
            await create_notification(
                user_id=user_id,
                title="⚠️ Aktivitas Akan Berakhir",
                message=notif_message,
                notification_type="schedule_ending",
                related_id=schedule["id"]
            )
            await db.schedules.update_one(
                {"id": schedule["id"]},
                {"$set": {"notified_30m_before_end": True}}
            )
            logging.info(f"[CRON] Sent 30m-before-end notification for schedule {schedule['id']} to user {user_id}")
        # ---- 3. Auto-Finish / Auto-Expire ----
        schedules_past_end = await db.schedules.find({
            "auto_finished": {"$ne": True},
            "end_date": {
                "$lte": now.isoformat()
            }
        }, {"_id": 0}).to_list(500)
        for schedule in schedules_past_end:
            schedule_id = schedule["id"]
            user_id = schedule["user_id"]
            site_name = schedule.get("site_name", "Unknown")
            user_name = schedule.get("user_name", "System")
            division = schedule.get("division", "")
            # Get the latest activity for this schedule
            latest_activity = await db.activities.find_one(
                {"schedule_id": schedule_id},
                {"_id": 0},
                sort=[("created_at", -1)]
            )
            current_status = latest_activity["status"] if latest_activity else None
            auto_time = datetime.now(LOCAL_TZ)
            if current_status in ["In Progress", "On Hold"]:
                # Auto-finish: activity was started/on hold
                activity_doc = {
                    "id": str(uuid.uuid4()),
                    "schedule_id": schedule_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "division": division,
                    "action_type": "auto_finish",
                    "status": "Finished",
                    "notes": f"Otomatis diselesaikan oleh sistem pada {auto_time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "reason": None,
                    "latitude": None,
                    "longitude": None,
                    "progress_updates": [],
                    "created_at": auto_time.isoformat(),
                    "updated_at": auto_time.isoformat()
                }
                await db.activities.insert_one(activity_doc)
                # Send confirmation notification
                notif_message = f"Aktivitas di *{site_name}* telah selesai otomatis oleh sistem."
                await create_notification(
                    user_id=user_id,
                    title="✅ Aktivitas Selesai Otomatis",
                    message=notif_message,
                    notification_type="auto_finish",
                    related_id=schedule_id
                )
                logging.info(f"[CRON] Auto-finished schedule {schedule_id} for user {user_id}")
            elif current_status is None:
                # Never started -> mark as Expired
                activity_doc = {
                    "id": str(uuid.uuid4()),
                    "schedule_id": schedule_id,
                    "user_id": user_id,
                    "user_name": user_name,
                    "division": division,
                    "action_type": "auto_expire",
                    "status": "Expired",
                    "notes": f"Jadwal tidak dimulai. Otomatis ditandai expired oleh sistem pada {auto_time.strftime('%Y-%m-%d %H:%M:%S')}",
                    "reason": None,
                    "latitude": None,
                    "longitude": None,
                    "progress_updates": [],
                    "created_at": auto_time.isoformat(),
                    "updated_at": auto_time.isoformat()
                }
                await db.activities.insert_one(activity_doc)
                notif_message = f"Jadwal di *{site_name}* telah ditandai *Expired* karena tidak dimulai."
                await create_notification(
                    user_id=user_id,
                    title="❌ Jadwal Expired",
                    message=notif_message,
                    notification_type="auto_expire",
                    related_id=schedule_id
                )
                logging.info(f"[CRON] Marked schedule {schedule_id} as Expired for user {user_id}")
            # Mark schedule as auto_finished regardless (to prevent reprocessing)
            await db.schedules.update_one(
                {"id": schedule_id},
                {"$set": {"auto_finished": True}}
            )
        # ---- 4. Periodic Progress Fallback (Ghost Logs) ----
        # Find all In Progress activities to check for pings/heartbeats
        active_activities = await db.activities.find({
            "status": "In Progress"
        }, {"_id": 0}).to_list(500)
        
        for activity in active_activities:
            activity_id = activity["id"]
            updated_at_str = activity.get("updated_at")
            if not updated_at_str:
                continue
                
            try:
                last_update = datetime.fromisoformat(updated_at_str)
                # Ensure last_update is offset-aware for comparison
                if last_update.tzinfo is None:
                    last_update = last_update.replace(tzinfo=timezone.utc)
            except (ValueError, TypeError):
                continue
                
            # If no heartbeat for > 15 minutes, insert a ghost log
            # We use UTC comparison as updated_at is usually ISO UTC
            now_utc = datetime.now(timezone.utc)
            if (now_utc - last_update) > timedelta(minutes=15):
                # Check if this activity is still within its scheduled time
                schedule = await db.schedules.find_one({"id": activity["schedule_id"]}, {"_id": 0})
                if schedule and schedule.get("end_date"):
                    try:
                        end_dt = datetime.fromisoformat(schedule["end_date"])
                        if end_dt.tzinfo is None:
                            end_dt = end_dt.replace(tzinfo=timezone.utc)
                        
                        if now_utc > end_dt:
                            # Too late for ghost logs, let auto-finish handle it
                            continue
                    except (ValueError, TypeError):
                        pass

                ghost_update = {
                    "timestamp": now_utc.isoformat(),
                    "update_text": "Sedang proses pengerjaan (System Generated - Page Closed)",
                    "user_name": activity["user_name"],
                    "latitude": None,
                    "longitude": None,
                    "is_auto": True
                }
                
                await db.activities.update_one(
                    {"id": activity_id},
                    {
                        "$push": {"progress_updates": ghost_update},
                        "$set": {"updated_at": now_utc.isoformat()}
                    }
                )
                logging.info(f"[CRON] Inserted server-side fallback log for activity {activity_id}")
    except Exception as e:
        logging.error(f"[CRON] Error in schedule notification cron job: {e}")
# ============ SCHEDULER INSTANCE ============
_scheduler = None
async def start_scheduler():
    """Start APScheduler on app startup."""
    global _scheduler
    _scheduler = AsyncIOScheduler()
    _scheduler.add_job(
        schedule_notification_cron_job,
        IntervalTrigger(seconds=60),
        id="schedule_notification_cron",
        name="Schedule Notification & Auto-Finish Cron",
        replace_existing=True
    )
    _scheduler.start()
    logging.info("[CRON] Schedule notification cron job started (runs every 60 seconds)")
async def stop_scheduler():
    """Stop APScheduler on app shutdown."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown()
        logging.info("[CRON] Schedule notification cron job stopped")
