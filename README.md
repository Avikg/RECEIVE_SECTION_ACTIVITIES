# POWER DISCOM Receive Section — Document Management System

A web-based document tracking and routing system for the WBSEDCL Receive Section. Built with a Flask + SQLite backend and a single-page vanilla JS frontend. Designed to run on a local network — no internet required.

---

## Features

- **Document Management** — Receive, track, and route Notesheets, Bills, and Letters with full movement history
- **Role-Based Access Control** — Admin, Section Head, and Sectional Staff roles with enforced routing rules
- **Document Routing** — Transfer documents between users/sections; every movement is recorded
- **Dashboard** — Live stats: active documents, overdue items, document type breakdown
- **Search** — Search across all documents by number, subject, type, or section
- **Reports** — Holdings report with days-pending indicators and overdue highlighting
- **Activity Log** — Three-tab admin log:
  - Document Actions — every receive, route, and transfer by any user
  - Login / IP Log — all login, logout, and failed login attempts with IP address and browser info
  - Sessions — login/logout times, session duration, and active session status
- **User Management** — Create, edit, activate/deactivate users
- **Section Management** — Full CRUD for office sections
- **Database Backup** — One-click DB download from the sidebar (admin only)
- **Pagination** — All large tables paginated (10–15 rows per page)
- **Standalone EXE** — Can be built into a single `.exe` for deployment on machines without Python

---

## Tech Stack

| Layer    | Technology                        |
|----------|-----------------------------------|
| Backend  | Python 3, Flask                   |
| Database | SQLite (WAL mode)                 |
| Auth     | JWT (PyJWT) + bcrypt              |
| Frontend | Vanilla JS, single HTML file      |
| Server   | Flask dev server on port 3000     |

---

## Installation (Development / Source)

### Requirements

- Python 3.8+
- pip

### Steps

```bash
# 1. Clone the repo
git clone https://github.com/Avikg/RECEIVE_SECTION_ACTIVITIES.git
cd RECEIVE_SECTION_ACTIVITIES

# 2. Install dependencies
pip install -r requirements.txt

# 3. Start the server
python app.py
```

Then open **http://localhost:3000** in your browser.

**On Windows**, just double-click **`START.bat`** — it installs dependencies and launches the server automatically.

---

## Standalone EXE Deployment (No Python Required)

For deploying to a machine where Python is not installed:

### Build the EXE (run once on your dev machine)

```
Double-click BUILD.bat
```

This installs PyInstaller, builds everything, and produces:

```
WBSEDCL_Release\
    WBSEDCL.exe     <- single file, no other dependencies
```

### Deploy to another PC

1. Copy `WBSEDCL.exe` to any folder on the target machine
2. If migrating an existing database, copy `wbsedcl.db` into the **same folder** as the exe
3. Double-click `WBSEDCL.exe`
4. The browser opens automatically to `http://localhost:3000`
5. Login with `admin` / `admin123`

> **Note:** First launch takes 5-10 seconds while the exe extracts itself. Subsequent launches are faster.
> The database file (`wbsedcl.db`) is always saved in the same folder as the exe.

---

## Default Login

| Username | Password   | Role  |
|----------|------------|-------|
| `admin`  | `admin123` | Admin |

> Change the admin password immediately after first login via **User Management**.

---

## Roles and Permissions

| Role                                  | Capabilities                                                  |
|---------------------------------------|---------------------------------------------------------------|
| **Admin**                             | Full access — users, sections, activity logs, DB backup       |
| **Head**                              | Route documents to any active user in the system              |
| **Sectional Staff (Receive Section)** | Receive new documents; route to anyone                        |
| **Sectional Staff (Other Sections)**  | Route documents to their own Section Head only                |

---

## Document Fields

When receiving a new document:

| Field                    | Description                                        |
|--------------------------|----------------------------------------------------|
| Document Type            | Notesheet / Bill / Letter                          |
| Document Number          | Unique reference number                            |
| Subject                  | Brief description of the document                  |
| Received Date            | Date of physical receipt                           |
| CCC Forward No           | CCC forwarding reference number                    |
| CCC Forward Date         | Date forwarded by CCC                              |
| From Whom Received       | Source section (dropdown) or free-text             |
| Contractor/Consumer Name | Applicable for Bills and Letters                   |
| Description / Remarks    | Optional additional notes                          |

---

## Activity Logging

### Login / IP Log

Every login attempt (successful or failed) is recorded with:

- Timestamp
- IP address of the client
- Browser / User-Agent string
- Action type: `login`, `logout`, or `failed_login`
- Username attempted

### Session Tracking

Each login session records:

- Login time and logout time
- Session duration (calculated automatically)
- Active session status (whether the user is currently logged in)

### Document Actions

Every document movement records:

- Which user sent it and to whom
- Source and destination section
- Timestamp
- Notes/remarks attached to the transfer

All three logs are accessible under **Activity Log** in the admin sidebar and support pagination and filtering by user.

---

## Database Backup

Admins see a **Backup DB** button in the sidebar. Clicking it downloads a complete, consistent snapshot of `wbsedcl.db` using SQLite's built-in online backup API — safe with concurrent connections and WAL mode. The downloaded file is named `wbsedcl_backup_YYYYMMDD_HHMMSS.db`.

To restore a backup, stop the server, replace `wbsedcl.db` with the backup file (rename it to `wbsedcl.db`), and restart.

---

## Project Structure

```
├── app.py                  # Flask backend — all API routes and DB logic
├── public/
│   └── index.html          # Single-page frontend (HTML + CSS + JS)
├── requirements.txt        # Python dependencies
├── START.bat               # Windows one-click launcher (source/dev)
├── BUILD.bat               # Builds standalone WBSEDCL.exe via PyInstaller
├── WBSEDCL.spec            # PyInstaller build configuration
└── wbsedcl.db              # SQLite database (auto-created on first run)
```

---

## API Endpoints

| Method | Endpoint                      | Auth  | Description                              |
|--------|-------------------------------|-------|------------------------------------------|
| POST   | `/api/auth/login`             | None  | Login, returns JWT + session ID          |
| POST   | `/api/auth/logout`            | JWT   | Logout, closes active session            |
| GET    | `/api/auth/me`                | JWT   | Get current user info                    |
| GET    | `/api/documents`              | JWT   | List documents (filterable)              |
| POST   | `/api/documents`              | JWT   | Receive a new document                   |
| GET    | `/api/documents/:id`          | JWT   | Get single document with full history    |
| POST   | `/api/documents/:id/transfer` | JWT   | Route / transfer a document              |
| GET    | `/api/users`                  | Admin | List all users                           |
| POST   | `/api/users`                  | Admin | Create a new user                        |
| PUT    | `/api/users/:id`              | Admin | Update user details                      |
| GET    | `/api/users/recipients`       | JWT   | Get routable recipients for current user |
| GET    | `/api/sections`               | JWT   | List all sections                        |
| POST   | `/api/sections`               | Admin | Create a new section                     |
| PUT    | `/api/sections/:id`           | Admin | Update a section                         |
| DELETE | `/api/sections/:id`           | Admin | Delete a section                         |
| GET    | `/api/reports/holdings`       | JWT   | Holdings report with days-pending        |
| GET    | `/api/activity`               | JWT   | Document movement log                    |
| GET    | `/api/admin/ip-logs`          | Admin | Login/logout IP log                      |
| GET    | `/api/admin/sessions`         | Admin | Session log                              |
| GET    | `/api/admin/user-actions`     | Admin | Per-user document actions                |
| GET    | `/api/admin/backup`           | Admin | Download full database backup            |

---

## Requirements File

```
flask
PyJWT
bcrypt
```

Install with:

```bash
pip install -r requirements.txt
```

---

## Known Limitations

- Designed for local network / intranet use only — not hardened for public internet exposure
- Single-server, single-process — suitable for small office use (up to ~50 concurrent users)
- The JWT secret key should be changed to a longer random string before production use
- No email notifications — document routing is visible only within the application

---

## License

Internal use — WBSEDCL Receive Section.
