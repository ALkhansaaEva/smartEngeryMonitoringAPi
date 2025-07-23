from sqlalchemy import Column, Time, String, Integer, Float, DateTime, Boolean, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False)
    hashed_password = Column(String(256), nullable=False)
    role = Column(String(20), default="user")  # admin | user
    is_active = Column(Boolean, default=True)

    devices = relationship("Device", back_populates="owner")

class Device(Base):
    __tablename__ = "devices"

    id             = Column(String(36), primary_key=True)    # UUID
    name           = Column(String(100), nullable=False)
    house_id       = Column(Integer, nullable=False)
    appliance      = Column(String(15), nullable=False)     # Appliance1..9
    email          = Column(String(100))
    recommend_only = Column(Boolean, default=True)
    auto_off       = Column(Boolean, default=False)
    owner_id       = Column(Integer, ForeignKey("users.id"))  # FK to users.id

    owner = relationship("User", back_populates="devices")
    schedules = relationship(
        "DeviceSchedule",
        back_populates="device",
        cascade="all, delete-orphan"
    )

class DeviceSchedule(Base):
    __tablename__ = "schedules"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    device_id           = Column(String(36), ForeignKey("devices.id"), nullable=False)
    start_time          = Column(Time, nullable=False)     
    end_time            = Column(Time, nullable=False)    
    days                = Column(String(255), nullable=False)
    send_email_reminder = Column(Boolean, default=False)

    device = relationship("Device", back_populates="schedules")

class Reading(Base):
    __tablename__ = "readings"

    id        = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id"), nullable=False)
    ts        = Column(DateTime, nullable=False)
    watts     = Column(Float, nullable=False)
