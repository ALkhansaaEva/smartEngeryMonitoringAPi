# ⚡️ Smart Energy Monitoring & Control API

<!-- <p align="center">
  <img src="https://raw.githubusercontent.com/ALkhansaaEva/smartEngeryMonitoringAPi/main/static/logo.svg" width="120" alt="logo"/>
</p> -->
<p align="center"><b>FastAPI-powered IoT backend for energy visibility, ML insights & smart automation.</b></p>

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-%F0%9F%9A%80-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![Docker Ready](https://img.shields.io/badge/docker-ready-blue?logo=docker)](https://docs.docker.com)
[![License](https://img.shields.io/github/license/ALkhansaaEva/smartEngeryMonitoringAPi)](LICENSE)

> **Why?** Because raw kWh numbers are useless unless they **drive action**. This API ingests high-frequency readings, predicts appliance states with ML, then triggers alerts or auto-shutdowns ✨.

---

## ✨ Features

|     | Capability                                                               |
| --- | ------------------------------------------------------------------------ |
| 🔒  | **JWT Auth & RBAC** – secure token flow, `admin` vs `user` roles         |
| 🏠  | **Hierarchical Data Model** – houses ➜ devices ➜ channels                |
| 🤖  | **ML-powered Predictions** – Decision-Tree / KNN pipelines per appliance |
| 💡  | **Smart Automation** – email alerts, auto-off relays & schedule rules    |
| 📈  | **Instant Analytics** – per-device summaries & live ON/OFF status        |
| 📦  | **Containerised** – one-command bootstrap via Docker Compose             |
| 🛡️  | **Clean Code** – Pydantic, SQLAlchemy, Alembic-ready                     |
| 🚀  | **Fast** – async FastAPI + Uvicorn, \~40k rps on M2 MBP                  |

---

## 🧰 Tech Stack

| Layer     | Tech                                           |
| --------- | ---------------------------------------------- |
| **API**   | FastAPI (v0.110), Uvicorn, Pydantic            |
| **DB**    | MySQL 9, SQLAlchemy ORM                        |
| **Auth**  | OAuth2 Password (JWT)                          |
| **ML**    | Scikit-learn, joblib pipelines                 |
| **Infra** | Docker Compose, GitHub Actions (_coming soon_) |

---

## 🚀 Quick Start

```bash
# 1️⃣ Clone
$ git clone https://github.com/ALkhansaaEva/smartEngeryMonitoringAPi.git
$ cd smartEngeryMonitoringAPi

# 2️⃣ Copy & edit environment vars
$ cp .env.example .env  # then tweak SMTP, SECRET_KEY, …

# 3️⃣ Spin up stack (API + MySQL)
$ docker compose up -d --build

# 4️⃣ Open swagger
$ open http://localhost:8000/docs   # or just visit in your browser
```

> 📒 The `models/` folder is auto-mounted so you can hot-swap joblib pipelines without rebuilding.

---

## 🗝️ Environment Variables

> All live in `.env` (see `.env.example`).

| Key                        | Default                                                     | Description                     |
| -------------------------- | ----------------------------------------------------------- | ------------------------------- |
| `SECRET_KEY`               | _random_                                                    | JWT signing secret              |
| `DB_URL`                   | `mysql+pymysql://energy_user:energy_pass@mysql:3306/energy` | SQLAlchemy DSN                  |
| `SMTP_HOST`                | `smtp.gmail.com`                                            | Mail gateway                    |
| `SMTP_PORT`                | `465`                                                       | 465 = SSL, 587 = STARTTLS       |
| `SMTP_USER`                | –                                                           | SMTP username                   |
| `SMTP_PASS`                | –                                                           | SMTP password                   |
| `ALERT_FROM`               | –                                                           | Sender address for alerts       |
| `ML_MODELS_DIR`            | `models/`                                                   | Folder with `Appliance*.joblib` |
| `SMTP_SSL`                 | `true`                                                      | Force implicit SSL mode         |
| `FIREBASE_SERVICE_ACCOUNT` | –                                                           | (Optional) FCM push creds       |

---

## 🛣️ API Surface

Full OpenAPI JSON + Swagger UI lives at `/docs` and ReDoc at `/redoc`. Below is the human-friendly cheat-sheet.

<details>
<summary>⚙️ Auth</summary>

```http
POST /token
Content-Type: application/x-www-form-urlencoded

username=ALkhansaaEva@example.com&password=SuperSecret123

```

</details>

<details>
<summary>👤 Users</summary>

```http
POST /users
Content-Type: application/json

{
  "full_name": "ALkhansaaEva",
  "email": "ALkhansaaEva@example.com",
  "password": "SuperSecret123"
}
```

```http
POST /users/change-password
Authorization: Bearer <JWT>

{
  "old_password": "SuperSecret123",
  "new_password": "EvenMoreSecret456"
}
```

</details>

<details>
<summary>📟 Devices</summary>

```http
POST /devices
Authorization: Bearer <JWT>
Content-Type: application/json

{
  "name": "AC Living Room",
  "house_id": 1,
  "appliance": "Appliance2",
  "email": "alerts@home.io",
  "recommend_only": true,
  "auto_off": false
}
```

```http
GET /devices | GET /devices/{device_id}
```

</details>

<details>
<summary>🗓️ Schedules</summary>

```http
POST /schedules

{
  "device_id": "59fc1e1e-3c99-42c2-a1d8-0f6e1ddc9e28",
  "start_time": "08:00",
  "end_time": "10:00",
  "days": ["Mon","Tue","Wed"],
  "send_email_reminder": true
}
```

</details>

<details>
<summary>⚡ Energy & Readings</summary>

```http
POST /houses/{house_id}/reading

{
  "timestamp": "2025-07-15T12:34:56Z",
  "aggregate": 3400.5,
  "appliances": {
    "Appliance1": 1200,
    "Appliance2":   40,
    "Appliance3":    0
  }
}
```

```http
GET /devices/{device_id}/energy-summary
GET /houses/{house_id}/devices/{device_id}/status
```

</details>

---

## 🗄️ Project Structure

```text
.
├─ app/                 # FastAPI application
│  ├─ main.py           # Entrypoint & routers
│  ├─ crud.py           # DB helpers (SQLAlchemy)
│  ├─ ml_model.py       # Scikit-learn wrapper
│  ├─ schemas.py        # Pydantic models
│  ├─ notifications.py  # SMTP alert helper
│  └─ …
├─ models/              # *.joblib pipelines
├─ static/              # SPA (login + dashboard)
├─ docker-compose.yml   # app + db
├─ Dockerfile           # production image
└─ requirements.txt
```

---

## 🖥️ Local Dev (without Docker)

```bash
# start MySQL in Docker only
docker compose -f docker-compose-database.yml up -d

# create venv & install deps
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# run FastAPI hot-reload
uvicorn app.main:app --reload --port 8000
```

---

## 🤝 Contributing

1. **Fork** the repo and create your branch: `git checkout -b feat/amazing-thing`
2. **Commit** with conventional messages.
3. **Lint & Test** locally (tests coming soon).
4. **PR** to the `main` branch – we review fast ⚡.

---

<p align="center">Made with ☕️ & ⚡ by <a href="https://github.com/ALkhansaaEva">ALkhansaaEva</a></p>
