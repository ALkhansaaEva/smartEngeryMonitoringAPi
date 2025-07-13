import os
from datetime import datetime, timedelta
from typing import List

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from jose import JWTError, jwt
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

# Local imports
from . import models, schemas, crud, ml_model, notifications

# Load environment variables
load_dotenv()

# Database setup
engine = create_engine(os.getenv("DB_URL"), future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, future=True)
models.Base.metadata.create_all(engine)

# JWT configuration
SECRET_KEY = os.getenv("SECRET_KEY", "secret")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# Dependency: DB session
def db_dep():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# OAuth2 scheme
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

# FastAPI app
app = FastAPI(title="Energy-IoT API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# Utility: create JWT token
def create_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# Dependency: get current user
def get_current_user(db: Session = Depends(db_dep), token: str = Depends(oauth2_scheme)):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = crud.get_user_by_email(db, email)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Dependency: admin-only
def require_admin(user=Depends(get_current_user)):
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admins only")
    return user

# ---- Auth Endpoints ----

@app.post("/token")
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(db_dep)
):
    user = crud.verify_user(db, form.username, form.password)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid credentials")
    token = create_token({"sub": user.email})
    return {"access_token": token, "token_type": "bearer"}

@app.post("/users", response_model=schemas.UserOut)
def register_user(
    u: schemas.UserCreate,
    db: Session = Depends(db_dep)
):
    if crud.get_user_by_email(db, u.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, u)

@app.post("/users/change-password")
def change_pw(
    data: schemas.ChangePassword,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    ok = crud.change_user_password(db, user.id, data.old_password, data.new_password)
    if not ok:
        raise HTTPException(status_code=403, detail="Wrong password")
    return {"detail": "Password changed"}

# ---- Protected User Endpoints ----

@app.post("/devices", response_model=schemas.DeviceOut)
def add_dev(
    p: schemas.DeviceCreate,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    """Create a new device tied to the authenticated user."""
    return crud.create_device(db, p, user.id)

@app.get("/devices", response_model=List[schemas.DeviceOut])
def all_devs(
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    """List devices owned by the authenticated user."""
    return crud.list_devices(db, user.id)

@app.get("/devices/{id}", response_model=schemas.DeviceOut)
def one_device(
    id: str,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    d = crud.get_device(db, id)
    if not d or d.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Not found")
    return d

@app.put("/devices/{id}", response_model=schemas.DeviceOut)
def update_dev(
    id: str,
    p: schemas.DeviceUpdate,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    d = crud.get_device(db, id)
    if not d or d.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud.update_device(db, id, p)
    return crud.get_device(db, id)

@app.delete("/devices/{id}")
def delete_dev(
    id: str,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    d = crud.get_device(db, id)
    if not d or d.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    crud.delete_device(db, id)
    return {"detail": "deleted"}

# ---- Scheduling ----

@app.post("/schedules", response_model=schemas.ScheduleOut)
def add_schedule(
    s: schemas.ScheduleCreate,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    dev = crud.get_device(db, s.device_id)
    if not dev or dev.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return crud.create_schedule(db, s)

@app.get("/devices/{device_id}/schedules", response_model=List[schemas.ScheduleOut])
def list_schedules(
    device_id: str,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    dev = crud.get_device(db, device_id)
    if not dev or dev.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return crud.list_schedules_for_device(db, device_id)

@app.put("/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    s: schemas.ScheduleUpdate,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    crud.update_schedule(db, schedule_id, s)
    return {"detail": "Updated"}

@app.delete("/schedules/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    crud.delete_schedule(db, schedule_id)
    return {"detail": "Deleted"}

# ---- Energy Summary ----

@app.get("/devices/{device_id}/energy-summary", response_model=schemas.EnergySummary)
def get_energy_summary(
    device_id: str,
    db: Session = Depends(db_dep),
    user=Depends(get_current_user)
):
    dev = crud.get_device(db, device_id)
    if not dev or dev.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return crud.energy_summary(db, device_id)

# ---- Real-time Reading & Control ----

@app.post("/houses/{house_id}/reading", response_model=List[schemas.ActionOut])
def ingest_readings(
    house_id: int,
    s: schemas.BulkReading,
    bg: BackgroundTasks,
    db: Session = Depends(db_dep)
):
    # Save raw readings
    for channel, val in s.appliances.items():
        devices = crud.by_house_appliances(db, house_id, channel)
        for d in devices:
            crud.add_reading(db, d.id, schemas.ReadingIn(timestamp=s.timestamp, watts=val))

    # Predict actions
    actions = ml_model.predict_actions({
        "Time": pd.to_datetime(s.timestamp),
        "Aggregate": s.aggregate,
        **s.appliances
    })

    # Handle each device
    resp = []
    for channel, act in actions.items():
        devices = crud.by_house_appliances(db, house_id, channel)
        for d in devices:
            # Alerts & auto-off
            if d.recommend_only and d.email:
                bg.add_task(
                    notifications.send_email,
                    d.email,
                    f"[Alert] {d.name} → {act}",
                    f"{d.name} predicted {act} at {s.timestamp}"
                )
            if d.auto_off and act == "OFF":
                print(f"AUTO-OFF relay for {d.id}")
            resp.append({
                "device_id": d.id,
                "name":      d.name,
                "appliance": d.appliance,
                "action":    act
            })
    return resp

# ---- Device Live Status ----

@app.get(
    "/houses/{house_id}/devices/{device_id}/status",
    response_model=schemas.DeviceStatus,
    summary="آخر حالة للجهاز (ON/OFF) داخل منزل معيّن"
)
def device_status(
    house_id: int,
    device_id: str,
    db: Session = Depends(db_dep)
):
    d = crud.get_device(db, device_id)
    if not d or d.house_id != house_id:
        raise HTTPException(status_code=404, detail="Device not found in this house")
    rd = crud.latest_reading(db, device_id)
    if not rd:
        return {"device_id": device_id, "house_id": house_id, "status": "UNKNOWN"}
    status = "ON" if rd.watts >= 10 else "OFF"
    return {
        "device_id": device_id,
        "house_id":  house_id,
        "timestamp": rd.ts,
        "watts":     rd.watts,
        "status":    status
    }

# ---- Statistics ----

@app.get("/devices/{id}/stats", response_model=schemas.DeviceStats)
def stats(
    id: str,
    db: Session = Depends(db_dep)
):
    if not crud.get_device(db, id):
        raise HTTPException(status_code=404)
    s = crud.stats(db, id)
    return {"id": id, **s}

# ---- Serve SPA & Static ----

# @app.get("/", response_class=FileResponse)
# async def serve_index():
#     return "static/index.html"

# @app.get("/manager", response_class=FileResponse)
# async def serve_manager():
#     return "static/devices.html"

app.mount("/static", StaticFiles(directory="static"), name="static")
