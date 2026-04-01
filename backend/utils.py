import base64
import os
import uuid
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import jwt
from passlib.context import CryptContext
import requests

from database import db, SECRET_KEY, ALGORITHM, TELEGRAM_BOT_TOKEN, ACCESS_TOKEN_EXPIRE_MINUTES

logger = logging.getLogger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()

MONITORING_SHIFTS = {
    "Shift Pagi": {"start": "07:00", "end": "16:00", "next_day": False},
    "Shift Siang": {"start": "13:00", "end": "22:00", "next_day": False},
    "Shift Malam": {"start": "22:00", "end": "07:00", "next_day": True},
}

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except Exception:
        raise credentials_exception
        
    user = await db.users.find_one({"id": user_id})
    if user is None:
        raise credentials_exception
    return user

async def get_current_admin(current_user: dict = Depends(get_current_user)):
    if current_user["role"] not in ["Admin", "SuperUser"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The user doesn't have enough privileges"
        )
    return current_user

def is_tech_op_admin(user: dict):
    return user["role"] in ["Admin", "SuperUser"] and user.get("department") == "Technical Operation"

def decode_base64_image(base64_string: str) -> Optional[bytes]:
    try:
        if "," in base64_string:
            base64_string = base64_string.split(",")[1]
        return base64.b64decode(base64_string)
    except Exception as e:
        logger.error(f"Error decoding base64 image: {e}")
        return None

async def send_telegram_message(chat_id: str, text: str):
    if not TELEGRAM_BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not configured. Skipping telegram notification.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    try:
        response = requests.post(url, json=payload, timeout=5)
        response.raise_for_status()
    except Exception as e:
        logger.error(f"Failed to send telegram message to {chat_id}: {e}")

async def create_notification(user_id: str, title: str, message: str, notification_type: str, related_id: Optional[str] = None):
    notification = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "title": title,
        "message": message,
        "type": notification_type,
        "related_id": related_id,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(notification)
    
    user = await db.users.find_one({"id": user_id})
    if user and user.get("telegram_id"):
        asyncio.create_task(send_telegram_message(user["telegram_id"], f"*{title}*\n{message}"))
