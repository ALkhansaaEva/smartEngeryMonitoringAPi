import os
from datetime import datetime, timedelta
from fastapi import Path
from typing import List, Dict

import pandas as pd
from dotenv import load_dotenv
from fastapi import (
    FastAPI, HTTPException, Depends,
    BackgroundTasks, Request
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import (
    OAuth2PasswordBearer, OAuth2PasswordRequestForm
)
from fastapi.responses import (
    FileResponse, HTMLResponse, RedirectResponse
)
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Local application modules
from . import models, schemas, crud, ml_model, notifications

# Load environment variables from .env
load_dotenv()

# -------------------------------------------------------------------
# Database configuration
# -------------------------------------------------------------------
DATABASE_URL = os.getenv("DB_URL")
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)

# Create all tables (if not exist)
models.Base.metadata.create_all(engine)

# -------------------------------------------------------------------
# JWT configuration
# -------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_ME")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# -------------------------------------------------------------------
# FastAPI application setup
# -------------------------------------------------------------------
app = FastAPI(title="Energy-IoT API", version="1.0.0")

# Allow all CORS origins (adjust in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Dependency: provide a database session
# -------------------------------------------------------------------
def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# -------------------------------------------------------------------
# OAuth2 password flow
# -------------------------------------------------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def create_access_token(data: Dict[str, str], expires_delta: timedelta = None) -> str:
    """Generate a signed JWT token with expiration."""
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
):
    """Decode JWT and retrieve the corresponding user."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if not email:
            raise HTTPException(status_code=401, detail="Invalid authentication token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

def require_admin(user=Depends(get_current_user)):
    """Ensure that the current user has an admin role."""
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user

# -------------------------------------------------------------------
# Authentication endpoints
# -------------------------------------------------------------------
@app.post("/token")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    """Authenticate user and return a JWT token."""
    user = crud.verify_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Incorrect username or password")
    token = create_access_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/users", response_model=schemas.UserOut)
def register_user(
    new_user: schemas.UserCreate,
    db: Session = Depends(get_db)
):
    """Register a new user account."""
    if crud.get_user_by_email(db, new_user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, new_user)

@app.post("/users/change-password")
def change_password(
    data: schemas.ChangePassword,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Allow authenticated user to change their password."""
    success = crud.change_user_password(db, current_user.id, data.old_password, data.new_password)
    if not success:
        raise HTTPException(status_code=403, detail="Old password is incorrect")
    return {"detail": "Password successfully changed"}

# -------------------------------------------------------------------
# Device management endpoints
# -------------------------------------------------------------------
@app.post("/devices", response_model=schemas.DeviceOut)
def create_device(
    device_in: schemas.DeviceCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Create a new IoT device for the authenticated user."""
    return crud.create_device(db, device_in, current_user.id)

@app.get("/devices", response_model=List[schemas.DeviceOut])
def list_devices(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Return all devices owned by the authenticated user."""
    return crud.list_devices(db, current_user.id)

@app.get("/devices/{device_id}", response_model=schemas.DeviceOut)
def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Fetch a single device, ensuring ownership."""
    device = crud.get_device(db, device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=404, detail="Device not found")
    return device

@app.put("/devices/{device_id}", response_model=schemas.DeviceOut)
def update_device(
    device_id: str,
    update_in: schemas.DeviceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Update device metadata (name, settings, etc.)."""
    device = crud.get_device(db, device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud.update_device(db, device_id, update_in)
    return crud.get_device(db, device_id)

@app.delete("/devices/{device_id}")
def remove_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete a device and all its readings."""
    device = crud.get_device(db, device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud.delete_device(db, device_id)
    return {"detail": "Device deleted"}

# -------------------------------------------------------------------
# Scheduling endpoints
# -------------------------------------------------------------------
@app.post("/schedules", response_model=schemas.ScheduleOut)
def add_schedule(
    schedule_in: schemas.ScheduleCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Add an on/off schedule for a device."""
    device = crud.get_device(db, schedule_in.device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")

    return crud.create_schedule(db, schedule_in)

@app.get("/devices/{device_id}/schedules", response_model=List[schemas.ScheduleOut])
def get_schedules(
    device_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """List all schedules for a specific device."""
    device = crud.get_device(db, device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return crud.list_schedules_for_device(db, device_id)

@app.put("/schedules/{schedule_id}")
def edit_schedule(
    schedule_id: int,
    schedule_update: schemas.ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Modify an existing schedule."""
    crud.update_schedule(db, schedule_id, schedule_update)
    return {"detail": "Schedule updated"}

@app.delete("/schedules/{schedule_id}")
def remove_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Delete a schedule by its ID."""
    crud.delete_schedule(db, schedule_id)
    return {"detail": "Schedule deleted"}

# -------------------------------------------------------------------
# Energy summary endpoint
# -------------------------------------------------------------------
@app.get("/devices/{device_id}/energy-summary", response_model=schemas.EnergySummary)
def energy_summary(
    device_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    """Return consumption totals: today, past week, past month."""
    device = crud.get_device(db, device_id)
    if not device or device.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return crud.energy_summary(db, device_id)

# -------------------------------------------------------------------
# Bulk reading ingestion & action prediction
# -------------------------------------------------------------------
@app.post("/houses/{house_id}/reading", response_model=List[schemas.ActionOut])
def ingest_bulk_readings(
    house_id: int,
    bulk: schemas.BulkReading,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db)
):
    """
    Store readings for each appliance, run the ML model
    to predict ON/OFF actions, then handle notifications/auto-off.
    """
    # Persist each channel reading
    for channel, watt in bulk.appliances.items():
        devices = crud.by_house_appliances(db, house_id, channel)
        for d in devices:
            crud.add_reading(db, d.id, schemas.ReadingIn(timestamp=bulk.timestamp, watts=watt))

    # Prepare DataFrame for model
    df_input = {
        "Time": pd.to_datetime(bulk.timestamp),
        "Aggregate": bulk.aggregate,
        **bulk.appliances
    }
    actions = ml_model.predict_actions(df_input)

    # Process predicted actions
    response = []
    for channel, action in actions.items():
        devices = crud.by_house_appliances(db, house_id, channel)
        for d in devices:
            # Send email alerts if enabled
            if d.recommend_only and d.email:
                background_tasks.add_task(
                    notifications.send_email,
                    d.email,
                    f"[Alert] {d.name} → {action}",
                    f"{d.name} predicted to {action} at {bulk.timestamp}"
                )
            # Perform relay auto-off if configured
            if d.auto_off and action == "OFF":
                print(f"AUTO-OFF relay for device {d.id}")
            response.append({
                "device_id": d.id,
                "name":      d.name,
                "appliance": d.appliance,
                "action":    action
            })
    return response

@app.post("/houses/{house_id}/reading/{device_id}", response_model=schemas.ActionOut)
def ingest_single_reading(
    house_id: int = Path(..., description="ID of the house"),
    device_id: str = Path(..., description="UUID of the device"),
    reading: schemas.ReadingIn = Depends(),
    background_tasks: BackgroundTasks = Depends(),
    db: Session = Depends(get_db)
):
    """
    Receive a single reading for a specific device in a given house.
    Store the reading, run the prediction model, and return the expected action.
    """
    # Verify that the device exists within the given house
    device = crud.get_device(db, device_id)
    if not device or device.house_id != house_id:
        raise HTTPException(status_code=404, detail="Device not found in this house")

    # Save the reading to the database
    crud.add_reading(db, device_id, reading)

    # Prepare input data for the prediction model (simplified example)
    df_input = {
        "Time": pd.to_datetime(reading.timestamp),
        "Aggregate": reading.watts,
        device.appliance: reading.watts
    }

    # Predict the action using the ML model
    actions = ml_model.predict_actions(df_input)  # returns dict like {"Appliance5": "OFF"}

    action = actions.get(device.appliance, "UNKNOWN")

    # Send notifications or perform other actions if necessary
    if device.recommend_only and device.email:
        background_tasks.add_task(
            notifications.send_email,
            device.email,
            f"[Alert] {device.name} → {action}",
            f"{device.name} predicted to {action} at {reading.timestamp}"
        )
    if device.auto_off and action == "OFF":
        print(f"AUTO-OFF relay for device {device_id}")

    # Return the predicted action result
    return schemas.ActionOut(
        device_id=device_id,
        name=device.name,
        appliance=device.appliance,
        action=action
    )

# -------------------------------------------------------------------
# Live device status endpoint
# -------------------------------------------------------------------
@app.get(
    "/houses/{house_id}/devices/{device_id}/status",
    response_model=schemas.DeviceStatus,
    summary="Get most recent ON/OFF status for a device"
)
def device_status(
    house_id: int,
    device_id: str,
    db: Session = Depends(get_db)
):
    """Fetch the latest reading and determine ON/OFF state."""
    device = crud.get_device(db, device_id)
    if not device or device.house_id != house_id:
        raise HTTPException(status_code=404, detail="Device not found in this house")

    latest = crud.latest_reading(db, device_id)
    if not latest:
        return {"device_id": device_id, "house_id": house_id, "status": "UNKNOWN"}

    status = "ON" if latest.watts >= 10 else "OFF"
    return {
        "device_id": device_id,
        "house_id":  house_id,
        "timestamp": latest.ts,
        "watts":     latest.watts,
        "status":    status
    }

# -------------------------------------------------------------------
# Historical stats endpoint
# -------------------------------------------------------------------
@app.get("/devices/{device_id}/stats", response_model=schemas.DeviceStats)
def device_stats(
    device_id: str,
    db: Session = Depends(get_db)
):
    """Compute average watts and total readings for a device."""
    if not crud.get_device(db, device_id):
        raise HTTPException(status_code=404, detail="Device not found")
    stats = crud.stats(db, device_id)
    return {"id": device_id, **stats}

# -------------------------------------------------------------------
# Serve frontend SPA and static assets
# -------------------------------------------------------------------
def validate_jwt(request: Request) -> bool:
    """Check for valid JWT in cookies or Authorization header."""
    token = (
        request.cookies.get("access_token") or
        request.headers.get("Authorization", "").removeprefix("Bearer ")
    )
    if not token:
        return False
    try:
        jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return True
    except JWTError:
        return False

@app.get("/", response_class=HTMLResponse)
async def serve_home(request: Request):
    """Redirect unauthenticated users to login, else serve app."""
    if not validate_jwt(request):
        return RedirectResponse("/static/login.html")
    return FileResponse("static/index.html")

@app.get("/manager", response_class=HTMLResponse)
async def serve_manager(request: Request):
    """Protected manager UI for device control."""
    if not validate_jwt(request):
        return RedirectResponse("/static/login.html")
    return FileResponse("static/devices.html")

@app.get("/login", response_class=FileResponse)
def serve_login():
    """Serve the login page."""
    return FileResponse("static/login.html")

# Mount the 'static' directory at /static
app.mount("/static", StaticFiles(directory="static"), name="static")
