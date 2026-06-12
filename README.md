# ⚡ POWER DISCOM Receive Section — Document Management System

A web-based document tracking and routing system for the WBSEDCL Receive Section. Built with Flask + SQLite backend and a single-page vanilla JS frontend.

---

## Features

- **Document Management** — Receive, track, and route Notesheets, Bills, and Letters
- **Role-Based Access** — Admin, Section Head, and Sectional Staff roles with enforced routing rules
- **Document Routing** — Transfer documents between sections with full movement trail
- **Dashboard** — Live stats: active documents, overdue items, document types breakdown
- **Search** — Search across all documents by number, subject, type, or section
- **Reports** — Holdings report with days-pending indicators
- **Activity Log** — Three-tab admin log:
  - 📄 Document Actions — every receive/route/transfer by any user
  - 🌐 Login / IP Log — all login, logout, and failed login attempts with IP address and browser
  - 🔑 Sessions — login/logout times, duration, and active session status
- **User Management** — Create, edit, activate/deactivate users
- **Section Management** — Full CRUD for office sections
- **Database Backup** — One-click DB download from the sidebar (admin only)
- **Pagination** — All large tables paginated (10–15 rows per page)

---

## Tech Stack

| Layer    | Technology |
|----------|-----------|
| Backend  | Python 3, Flask |
| Database | SQLite (WAL mode) |
| Auth     | JWT (PyJWT) + bcrypt |
| Frontend | Vanilla JS, single HTML file |
| Server   | Flask dev server on port 3000 |

---

## Installation

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

## Default Login

| Username | Password  | Role  |
|----------|-----------|-------|
| `admin`  | `admin123` | Admin |

> Change the admin password immediately after first login via User Management.

---

## Document Fields

When receiving a new document:

| Field | Description |
|-------|-------------|
| Document Type | Notesheet / Bill / Letter |
| Document Number | Unique reference number |
| Subject | Brief description |
| Received Date | Date of physical receipt |
| CCC Forward No | CCC forwarding reference number |
| CCC Forward Date | Date forwarded by CCC |
| From Whom Received | Source section (dropdown) or free-text |
| Contractor/Consumer Name | Applicable for Bills and Letters |

---

## Role & Routing Rules

| Role | Can Route To |
|------|-------------|
| **Sectional Staff** (non-Receive) | Their own Section Head only |
| **Receive Section Staff** | Any active user in the system |
| **Head / Admin** | Any active user in the system |

---

## Activity Logging

Every login attempt (successful or failed) is recorded with:
- Timestamp
- IP address
- Browser / User-Agent string
- Action type: `login`, `logout`, or `failed_login`

Session tracking records:
- Login time, logout time, and session duration
- Active session status

---

## Database Backup

Admins see a **💾 Backup DB** button in the sidebar. Clicking it downloads a complete, consistent snapshot of `wbsedcl.db` using SQLite's built-in backup API (safe with concurrent connections and WAL mode).

---

## Project Structure

```
├── app.py              # Flask backend — all API routes
├── public/
│   └── index.html      # Single-page frontend (HTML + CSS + JS)
├── requirements.txt    # Python dependencies
├── START.bat           # Windows one-click launcher
└── wbsedcl.db          # SQLite database (auto-created on first run)
```

---

## API Endpoints (summary)

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/auth/login` | Login, returns JWT + session ID |
| POST | `/api/auth/logout` | Logout, closes session |
| GET | `/api/documents` | List documents |
| POST | `/api/documents` | Receive new document |
| POST | `/api/documents/:id/transfer` | Route/transfer a document |
| GET | `/api/reports/holdings` | All active documents with days-pending |
| GET | `/api/activity` | Movement log |
| GET | `/api/admin/ip-logs` | Login/IP log (admin) |
| GET | `/api/admin/sessions` | Session log (admin) |
| GET | `/api/admin/user-actions` | Per-user document actions (admin) |
| GET | `/api/admin/backup` | Download database backup (admin) |

---

## License

Internal use — WBSEDCL Receive Section.
