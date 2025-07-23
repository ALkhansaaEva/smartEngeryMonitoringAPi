from enum import Enum
from uuid import UUID
from datetime import datetime, time
from sqlalchemy import Column, Time
from typing import Optional, Dict, List
from pydantic import BaseModel, Field, EmailStr

# ---- Users ----
class UserBase(BaseModel):
    full_name: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserOut(UserBase):
    id: int
    role: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class ChangePassword(BaseModel):
    old_password: str
    new_password: str

# ---- Energy Summary ----
class EnergySummary(BaseModel):
    today: float
    week: float
    month: float

# ---- Scheduling ----
class Day(str, Enum):
    Mon = "Mon"
    Tue = "Tue"
    Wed = "Wed"
    Thu = "Thu"
    Fri = "Fri"
    Sat = "Sat"
    Sun = "Sun"
class ScheduleBase(BaseModel):
    start_time: time               # Format "HH:MM"
    end_time: time                 # Format "HH:MM"
    days: List[Day]               # List of valid days using the Day Enum
    send_email_reminder: bool = False

class ScheduleCreate(ScheduleBase):
    device_id: UUID

class ScheduleUpdate(ScheduleBase):
    pass

class ScheduleOut(ScheduleBase):
    id: int
    device_id: UUID

# ---- Devices ----
class DeviceBase(BaseModel):
    name: str
    house_id: int
    appliance: str = Field(..., pattern=r"^Appliance[1-9]$")
    email: Optional[str]
    recommend_only: Optional[bool] = True
    auto_off: Optional[bool] = False

class DeviceCreate(DeviceBase):
    pass

class DeviceUpdate(DeviceBase):
    pass

class DeviceOut(DeviceBase):
    id: UUID
    owner_id: int    # added so client sees which user owns it

# ---- Readings ----
class ReadingIn(BaseModel):
    timestamp: datetime
    watts: float

class BulkReading(BaseModel):
    timestamp: datetime
    aggregate: float
    appliances: Dict[str, float]   # keys "Appliance1".."Appliance9"

# ---- Stats ----
class DeviceStats(BaseModel):
    id: UUID
    avg_watts: float
    total_readings: int

class DeviceStatus(BaseModel):
    device_id: UUID
    house_id: int
    timestamp: Optional[datetime] = None
    watts: Optional[float] = None
    status: str

class ActionOut(BaseModel):
    device_id: UUID
    name: str
    appliance: str  # channel name, e.g. "Appliance3"
    action: str     # "ON" or "OFF"
