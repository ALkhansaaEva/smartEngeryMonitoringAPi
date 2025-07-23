from uuid import uuid4
from sqlalchemy.orm import Session
from sqlalchemy import func
from . import models, schemas
from typing import List
from passlib.hash import bcrypt
from datetime import datetime, timedelta

# -------- Users --------

def create_user(db: Session, data: schemas.UserCreate):
    """
    Create a new user and hash the password.
    """
    hashed_pw = bcrypt.hash(data.password)
    user = models.User(
        full_name=data.full_name,
        email=data.email,
        hashed_password=hashed_pw,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user

def get_user_by_email(db: Session, email: str):
    """Retrieve a user by email"""
    return db.query(models.User).filter(models.User.email == email).first()

def verify_user(db: Session, email: str, password: str):
    """Verify credentials against stored hash"""
    user = get_user_by_email(db, email)
    if user and bcrypt.verify(password, user.hashed_password):
        return user
    return None

def change_user_password(db: Session, user_id: int, old_pw: str, new_pw: str):
    """Change password if old password matches"""
    user = db.query(models.User).get(user_id)
    if not user or not bcrypt.verify(old_pw, user.hashed_password):
        return False
    user.hashed_password = bcrypt.hash(new_pw)
    db.commit()
    return True

# -------- Devices --------

def create_device(db: Session, data: schemas.DeviceCreate, owner_id: int):
    """
    Create a new device record tied to a specific owner.
    """
    device = models.Device(
        id=str(uuid4()),
        owner_id=owner_id,
        **data.dict()
    )
    db.add(device)
    db.commit()
    db.refresh(device)
    return device

def list_devices(db: Session, owner_id: int):
    """
    List all devices belonging to a given owner.
    """
    return db.query(models.Device).filter(models.Device.owner_id == owner_id).all()

def get_device(db: Session, device_id: str):
    """Retrieve a device by its ID"""
    return db.get(models.Device, device_id)

def update_device(db: Session, device_id: str, data: schemas.DeviceUpdate):
    """Update device fields selectively"""
    db.query(models.Device) \
      .filter(models.Device.id == device_id) \
      .update(data.dict(exclude_none=True))
    db.commit()

def delete_device(db: Session, device_id: str):
    """Delete a device and its related readings"""
    db.query(models.Reading) \
      .filter(models.Reading.device_id == device_id) \
      .delete()
    db.query(models.Device) \
      .filter(models.Device.id == device_id) \
      .delete()
    db.commit()

# -------- Device Schedules --------

def create_schedule(db: Session, data: schemas.ScheduleCreate) -> schemas.ScheduleOut:
    """
    Create a new schedule and return a ScheduleOut (with days as List[str]).
    """
    # column 'start_time' و 'end_time' مُعرّفين كـ Time في الموديل، فلا حاجة لتحويلهم إلى str
    days_str = ",".join([d.value for d in data.days])

    schedule = models.DeviceSchedule(
        device_id=data.device_id,
        start_time=data.start_time,
        end_time=data.end_time,
        days=days_str,
        send_email_reminder=data.send_email_reminder
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    # هنا نحوّل days_str إلى قائمة قبل الإرجاع
    return schemas.ScheduleOut(
        id=schedule.id,
        device_id=schedule.device_id,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        days=schedule.days.split(","),
        send_email_reminder=schedule.send_email_reminder
    )


def update_schedule(db: Session, schedule_id: int, data: schemas.ScheduleUpdate):
    days_str = ",".join([d.value for d in data.days])
    db.query(models.DeviceSchedule) \
      .filter(models.DeviceSchedule.id == schedule_id) \
      .update({
          "start_time": data.start_time,
          "end_time": data.end_time,
          "days": days_str,
          "send_email_reminder": data.send_email_reminder
      })
    db.commit()

def list_schedules_for_device(db: Session, device_id: str) -> List[schemas.ScheduleOut]:
    schedules = db.query(models.DeviceSchedule).filter(models.DeviceSchedule.device_id == device_id).all()
    return [
        schemas.ScheduleOut(
            id=s.id,
            device_id=s.device_id,
            start_time=s.start_time,
            end_time=s.end_time,
            days=s.days.split(",") if s.days else [],
            send_email_reminder=s.send_email_reminder
        )
        for s in schedules
    ]

def delete_schedule(db: Session, schedule_id: int):
    db.query(models.DeviceSchedule).filter(models.DeviceSchedule.id == schedule_id).delete()
    db.commit()

# -------- Aggregated Consumption Stats --------

def energy_summary(db: Session, device_id: str):
    now = datetime.utcnow()
    start_of_day = datetime(now.year, now.month, now.day)
    last_week = now - timedelta(days=7)
    last_month = now - timedelta(days=30)

    # اليوم
    today_total = db.query(func.sum(models.Reading.watts)) \
        .filter(
            models.Reading.device_id == device_id,
            models.Reading.ts >= start_of_day
        ).scalar() or 0.0

    # الأسبوع
    week_total = db.query(func.sum(models.Reading.watts)) \
        .filter(
            models.Reading.device_id == device_id,
            models.Reading.ts >= last_week
        ).scalar() or 0.0

    # الشهر
    month_total = db.query(func.sum(models.Reading.watts)) \
        .filter(
            models.Reading.device_id == device_id,
            models.Reading.ts >= last_month
        ).scalar() or 0.0

    return {
        "today": round(today_total, 2),
        "week": round(week_total, 2),
        "month": round(month_total, 2)
    }

# -------- Readings --------

def add_reading(db: Session, did: str, rd: schemas.ReadingIn):
    db.add(models.Reading(device_id=did, ts=rd.timestamp, watts=rd.watts))
    db.commit()

def stats(db: Session, did: str):
    avg, cnt = db.query(
        func.avg(models.Reading.watts),
        func.count()
    ).filter(models.Reading.device_id == did).one()
    return {"avg_watts": avg or 0.0, "total_readings": cnt or 0}

# -------- Houses & Channels --------

def list_houses(db: Session):
    """
    Return a list of distinct house_id values.
    """
    rows = db.query(models.Device.house_id).distinct().all()
    return [r[0] for r in rows]

def list_devices_by_house(db: Session, house_id: int):
    """
    Return all Device objects for a given house_id.
    """
    return db.query(models.Device) \
             .filter(models.Device.house_id == house_id) \
             .all()

def by_house_appliance(db: Session, house: int, appl: str):
    """
    Legacy: returns the first device on that channel.
    """
    return db.query(models.Device) \
             .filter(
                 models.Device.house_id == house,
                 models.Device.appliance == appl
             ).first()

# -------- Latest Reading --------

def latest_reading(db: Session, did: str):
    """
    Return the most-recent Reading row for a given device_id
    """
    return (
        db.query(models.Reading)
          .filter(models.Reading.device_id == did)
          .order_by(models.Reading.ts.desc())
          .first()
    )

def by_house_appliances(db: Session, house: int, appl: str):
    """
    Returns *all* devices registered under the given house_id and channel (appl).
    """
    return db.query(models.Device) \
             .filter(
                 models.Device.house_id == house,
                 models.Device.appliance == appl
             ).all()
