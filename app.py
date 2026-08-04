# WBSEDCL Receive Section - Flask Backend
# Run: python app.py

from flask import Flask, request, jsonify, send_from_directory
import sqlite3, bcrypt, jwt, os, sys
from datetime import datetime, timedelta
from functools import wraps

# ── PATH RESOLUTION (works both normally and as a PyInstaller .exe) ───────────
if getattr(sys, 'frozen', False):
    # Running inside a PyInstaller bundle
    _BUNDLE_DIR = sys._MEIPASS                          # extracted files live here
    _EXE_DIR    = os.path.dirname(sys.executable)      # writable dir next to the .exe
else:
    _BUNDLE_DIR = os.path.dirname(os.path.abspath(__file__))
    _EXE_DIR    = _BUNDLE_DIR

_PUBLIC_DIR = os.path.join(_BUNDLE_DIR, 'public')
DB_FILE     = os.path.join(_EXE_DIR, 'wbsedcl.db')

app = Flask(__name__, static_folder=_PUBLIC_DIR, static_url_path='')
JWT_SECRET = 'wbsedcl-receive-secret-2024'

# ── DATABASE ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sections (
                id   INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            );
            CREATE TABLE IF NOT EXISTS users (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT NOT NULL,
                username   TEXT NOT NULL UNIQUE,
                password   TEXT NOT NULL,
                role       TEXT NOT NULL CHECK(role IN ('admin','head','sectional')),
                section_id INTEGER REFERENCES sections(id),
                active     INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS documents (
                id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                doc_type           TEXT NOT NULL CHECK(doc_type IN ('Notesheet','Bill','Letter')),
                doc_number         TEXT NOT NULL,
                subject            TEXT NOT NULL,
                description        TEXT,
                received_date      TEXT NOT NULL,
                ccc_forward_no          TEXT,
                ccc_forward_date        TEXT,
                from_whom               TEXT,
                contractor_consumer_name TEXT,
                current_holder_id  INTEGER REFERENCES users(id),
                current_section_id INTEGER REFERENCES sections(id),
                status             TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Closed','Archived')),
                created_by_id      INTEGER REFERENCES users(id),
                created_at         TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS movements (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id     INTEGER NOT NULL REFERENCES documents(id),
                from_user_id    INTEGER REFERENCES users(id),
                to_user_id      INTEGER NOT NULL REFERENCES users(id),
                from_section_id INTEGER REFERENCES sections(id),
                to_section_id   INTEGER REFERENCES sections(id),
                action          TEXT NOT NULL CHECK(action IN ('Received','Transferred','Forwarded','Routed','Closed')),
                remarks         TEXT,
                created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS ip_logs (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER REFERENCES users(id),
                username   TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                action     TEXT NOT NULL CHECK(action IN ('login','logout','failed_login')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            );
            CREATE TABLE IF NOT EXISTS sessions (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id       INTEGER NOT NULL REFERENCES users(id),
                ip_address    TEXT,
                user_agent    TEXT,
                logged_in_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                logged_out_at TEXT,
                is_active     INTEGER NOT NULL DEFAULT 1
            );
        """)
        row = db.execute("SELECT COUNT(*) as c FROM sections").fetchone()
        if row['c'] == 0:
            for s in ['HR Section','Divisional Manager','DCC','Accounts',
                      'AE/DE TECH 1','AE/DE TECH 2','Store','Receive']:
                db.execute("INSERT INTO sections (name) VALUES (?)", (s,))
            pw = bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
            db.execute(
                "INSERT INTO users (name,username,password,role,section_id) VALUES (?,?,?,?,?)",
                ('Administrator', 'admin', pw, 'admin', None)
            )
            db.commit()
            print("Default admin created — username: admin  password: admin123")

def migrate_db():
    """Migrate existing DB — add new columns and fix movements CHECK constraint."""
    conn = get_db()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(documents)").fetchall()}
        # Rename old ccc_receive_* → ccc_forward_* BEFORE adding new columns
        if 'ccc_receive_no' in cols and 'ccc_forward_no' not in cols:
            conn.execute("ALTER TABLE documents RENAME COLUMN ccc_receive_no TO ccc_forward_no")
            cols.add('ccc_forward_no'); cols.discard('ccc_receive_no')
            print("Renamed ccc_receive_no → ccc_forward_no")
        if 'ccc_receive_date' in cols and 'ccc_forward_date' not in cols:
            conn.execute("ALTER TABLE documents RENAME COLUMN ccc_receive_date TO ccc_forward_date")
            cols.add('ccc_forward_date'); cols.discard('ccc_receive_date')
            print("Renamed ccc_receive_date → ccc_forward_date")
        # Add any still-missing columns
        for col, defn in [
            ('ccc_forward_no',          'TEXT'),
            ('ccc_forward_date',        'TEXT'),
            ('from_whom',               'TEXT'),
            ('contractor_consumer_name','TEXT'),
        ]:
            if col not in cols:
                conn.execute(f"ALTER TABLE documents ADD COLUMN {col} {defn}")
                print(f"Added column documents.{col}")
        conn.commit()
        # Create ip_logs table if missing
        tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if 'ip_logs' not in tables:
            conn.execute("""CREATE TABLE ip_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER REFERENCES users(id),
                username TEXT NOT NULL,
                ip_address TEXT,
                user_agent TEXT,
                action TEXT NOT NULL CHECK(action IN ('login','logout','failed_login')),
                created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
            )""")
            print("Created ip_logs table")
        if 'sessions' not in tables:
            conn.execute("""CREATE TABLE sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL REFERENCES users(id),
                ip_address TEXT,
                user_agent TEXT,
                logged_in_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
                logged_out_at TEXT,
                is_active INTEGER NOT NULL DEFAULT 1
            )""")
            print("Created sessions table")
        conn.commit()
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='movements'").fetchone()
        if row and 'Routed' not in row['sql']:
            print("Migrating movements table to add Routed action...")
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript("""
                ALTER TABLE movements RENAME TO movements_old;
                CREATE TABLE movements (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    document_id     INTEGER NOT NULL REFERENCES documents(id),
                    from_user_id    INTEGER REFERENCES users(id),
                    to_user_id      INTEGER NOT NULL REFERENCES users(id),
                    from_section_id INTEGER REFERENCES sections(id),
                    to_section_id   INTEGER REFERENCES sections(id),
                    action          TEXT NOT NULL CHECK(action IN ('Received','Transferred','Forwarded','Routed','Closed')),
                    remarks         TEXT,
                    created_at      TEXT NOT NULL DEFAULT (datetime('now','localtime'))
                );
                INSERT INTO movements SELECT * FROM movements_old;
                DROP TABLE movements_old;
            """)
            conn.execute("PRAGMA foreign_keys = ON")
            conn.commit()
            print("Migration complete.")
    finally:
        conn.close()

init_db()
migrate_db()

# ── AUTH HELPERS ─────────────────────────────────────────────────────────────
def make_token(user):
    return jwt.encode({
        'id': user['id'], 'username': user['username'],
        'name': user['name'], 'role': user['role'],
        'section_id': user['section_id'],
        'exp': datetime.utcnow() + timedelta(hours=12)
    }, JWT_SECRET, algorithm='HS256')

def auth_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify(error='Unauthorized'), 401
        try:
            request.user = jwt.decode(token, JWT_SECRET, algorithms=['HS256'])
        except Exception:
            return jsonify(error='Invalid token'), 401
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.user.get('role') != 'admin':
            return jsonify(error='Admin only'), 403
        return f(*args, **kwargs)
    return wrapper

def days_since(dt_str):
    if not dt_str:
        return 0
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%d'):
        try:
            return (datetime.now() - datetime.strptime(dt_str, fmt)).days
        except ValueError:
            continue
    return 0

# ── STATIC ───────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return send_from_directory('public', 'index.html')

# ── AUTH ─────────────────────────────────────────────────────────────────────
@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    with get_db() as db:
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND active=1",
            (data.get('username', ''),)
        ).fetchone()
        ip  = request.headers.get('X-Forwarded-For', request.remote_addr)
        ua  = request.headers.get('User-Agent', '')[:500]
        if not user or not bcrypt.checkpw(data.get('password', '').encode(), user['password'].encode()):
            db.execute(
                "INSERT INTO ip_logs (user_id,username,ip_address,user_agent,action) VALUES (?,?,?,?,?)",
                (user['id'] if user else None, data.get('username',''), ip, ua, 'failed_login')
            )
            db.commit()
            return jsonify(error='Invalid credentials'), 401
        db.execute(
            "INSERT INTO ip_logs (user_id,username,ip_address,user_agent,action) VALUES (?,?,?,?,?)",
            (user['id'], user['username'], ip, ua, 'login')
        )
        cur = db.execute(
            "INSERT INTO sessions (user_id,ip_address,user_agent) VALUES (?,?,?)",
            (user['id'], ip, ua)
        )
        session_id = cur.lastrowid
        db.commit()
        sec = db.execute("SELECT name FROM sections WHERE id=?", (user['section_id'],)).fetchone() \
              if user['section_id'] else None
        return jsonify(
            token=make_token(user),
            session_id=session_id,
            user=dict(id=user['id'], name=user['name'], username=user['username'],
                      role=user['role'], section_id=user['section_id'],
                      section_name=sec['name'] if sec else None)
        )

@app.route('/api/auth/me')
@auth_required
def me():
    with get_db() as db:
        user = db.execute(
            "SELECT id,name,username,role,section_id,active,created_at FROM users WHERE id=?",
            (request.user['id'],)
        ).fetchone()
        sec = db.execute("SELECT name FROM sections WHERE id=?", (user['section_id'],)).fetchone() \
              if user['section_id'] else None
        return jsonify(**dict(user), section_name=sec['name'] if sec else None)

@app.route('/api/auth/logout', methods=['POST'])
@auth_required
def logout():
    data = request.json or {}
    session_id = data.get('session_id')
    ip  = request.headers.get('X-Forwarded-For', request.remote_addr)
    ua  = request.headers.get('User-Agent', '')[:500]
    with get_db() as db:
        db.execute(
            "INSERT INTO ip_logs (user_id,username,ip_address,user_agent,action) VALUES (?,?,?,?,?)",
            (request.user['id'], request.user['username'], ip, ua, 'logout')
        )
        if session_id:
            db.execute(
                "UPDATE sessions SET logged_out_at=datetime('now','localtime'),is_active=0 WHERE id=? AND user_id=?",
                (session_id, request.user['id'])
            )
        else:
            db.execute(
                "UPDATE sessions SET logged_out_at=datetime('now','localtime'),is_active=0 WHERE user_id=? AND is_active=1",
                (request.user['id'],)
            )
        db.commit()
    return jsonify(message='Logged out')

@app.route('/api/admin/ip-logs')
@auth_required
@admin_required
def get_ip_logs():
    user_id = request.args.get('user_id', '')
    limit   = min(int(request.args.get('limit', 200)), 500)
    where   = "WHERE l.user_id=?" if user_id else ""
    params  = [user_id] if user_id else []
    with get_db() as db:
        rows = db.execute(f"""
            SELECT l.*, u.name as user_name, u.section_id,
                   s.name as section_name
            FROM ip_logs l
            LEFT JOIN users u ON l.user_id=u.id
            LEFT JOIN sections s ON u.section_id=s.id
            {where}
            ORDER BY l.created_at DESC LIMIT ?
        """, params + [limit]).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/admin/sessions')
@auth_required
@admin_required
def get_sessions():
    user_id = request.args.get('user_id', '')
    limit   = min(int(request.args.get('limit', 200)), 500)
    where   = "WHERE s.user_id=?" if user_id else ""
    params  = [user_id] if user_id else []
    with get_db() as db:
        rows = db.execute(f"""
            SELECT s.*, u.name as user_name, u.username,
                   sec.name as section_name
            FROM sessions s
            JOIN users u ON s.user_id=u.id
            LEFT JOIN sections sec ON u.section_id=sec.id
            {where}
            ORDER BY s.logged_in_at DESC LIMIT ?
        """, params + [limit]).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/admin/user-actions')
@auth_required
@admin_required
def get_user_actions():
    """All document movements + receives done by a user or all users."""
    user_id = request.args.get('user_id', '')
    limit   = min(int(request.args.get('limit', 300)), 500)
    where   = "WHERE (m.from_user_id=? OR m.to_user_id=?)" if user_id else ""
    params  = [user_id, user_id] if user_id else []
    with get_db() as db:
        rows = db.execute(f"""
            SELECT m.id, m.action, m.remarks, m.created_at,
                   fu.name as from_name, fs.name as from_section,
                   tu.name as to_name,   ts.name as to_section,
                   d.doc_number, d.doc_type, d.subject
            FROM movements m
            LEFT JOIN users fu    ON m.from_user_id=fu.id
            LEFT JOIN sections fs ON m.from_section_id=fs.id
            LEFT JOIN users tu    ON m.to_user_id=tu.id
            LEFT JOIN sections ts ON m.to_section_id=ts.id
            LEFT JOIN documents d ON m.document_id=d.id
            {where}
            ORDER BY m.created_at DESC LIMIT ?
        """, params + [limit]).fetchall()
        return jsonify([dict(r) for r in rows])

# ── SECTIONS ─────────────────────────────────────────────────────────────────
@app.route('/api/sections')
@auth_required
def get_sections():
    with get_db() as db:
        return jsonify([dict(r) for r in db.execute("SELECT * FROM sections ORDER BY id").fetchall()])

@app.route('/api/sections', methods=['POST'])
@auth_required
@admin_required
def create_section():
    name = (request.json or {}).get('name', '').strip()
    if not name:
        return jsonify(error='Name required'), 400
    try:
        with get_db() as db:
            cur = db.execute("INSERT INTO sections (name) VALUES (?)", (name,))
            db.commit()
            return jsonify(id=cur.lastrowid, name=name, message='Section created')
    except sqlite3.IntegrityError:
        return jsonify(error='Section name already exists'), 400

@app.route('/api/sections/<int:sid>', methods=['PUT'])
@auth_required
@admin_required
def update_section(sid):
    name = (request.json or {}).get('name', '').strip()
    if not name:
        return jsonify(error='Name required'), 400
    with get_db() as db:
        if not db.execute("SELECT id FROM sections WHERE id=?", (sid,)).fetchone():
            return jsonify(error='Section not found'), 404
        try:
            db.execute("UPDATE sections SET name=? WHERE id=?", (name, sid))
            db.commit()
            return jsonify(message='Section updated')
        except sqlite3.IntegrityError:
            return jsonify(error='Section name already exists'), 400

@app.route('/api/sections/<int:sid>', methods=['DELETE'])
@auth_required
@admin_required
def delete_section(sid):
    with get_db() as db:
        users = db.execute(
            "SELECT COUNT(*) as c FROM users WHERE section_id=? AND active=1", (sid,)
        ).fetchone()
        docs = db.execute(
            "SELECT COUNT(*) as c FROM documents WHERE current_section_id=? AND status='Active'", (sid,)
        ).fetchone()
        if users['c'] > 0:
            return jsonify(error=f'Cannot delete: {users["c"]} active user(s) assigned to this section'), 400
        if docs['c'] > 0:
            return jsonify(error=f'Cannot delete: {docs["c"]} active document(s) in this section'), 400
        db.execute("DELETE FROM sections WHERE id=?", (sid,))
        db.commit()
        return jsonify(message='Section deleted')

# ── USERS ────────────────────────────────────────────────────────────────────
@app.route('/api/users')
@auth_required
def get_users():
    with get_db() as db:
        rows = db.execute("""
            SELECT u.id,u.name,u.username,u.role,u.section_id,u.active,u.created_at,s.name as section_name
            FROM users u LEFT JOIN sections s ON u.section_id=s.id ORDER BY u.id
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/users/heads')
@auth_required
def get_heads():
    with get_db() as db:
        rows = db.execute(
            "SELECT u.id,u.name,u.role,u.section_id,s.name as section_name"
            " FROM users u LEFT JOIN sections s ON u.section_id=s.id"
            " WHERE u.role IN ('admin','head') AND u.active=1 ORDER BY u.name"
        ).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/users/recipients')
@auth_required
def get_recipients():
    """Return the list of valid transfer recipients for the current user."""
    me = request.user
    with get_db() as db:
        # Check if user belongs to the Receive section
        is_receive_section = False
        if me.get('section_id'):
            sec = db.execute("SELECT name FROM sections WHERE id=?", (me['section_id'],)).fetchone()
            is_receive_section = sec and 'receive' in sec['name'].strip().lower()

        print(f"[recipients] caller id={me.get('id')} role={me.get('role')} section_id={me.get('section_id')}")
        if me['role'] == 'sectional' and not is_receive_section:
            # Normal non-head: only their own section head
            rows = db.execute(
                "SELECT u.id,u.name,u.role,u.section_id,s.name as section_name"
                " FROM users u LEFT JOIN sections s ON u.section_id=s.id"
                " WHERE u.role='head' AND u.section_id=? AND u.active=1 AND u.id!=?"
                " ORDER BY u.name",
                (me['section_id'], me['id'])
            ).fetchall()
        else:
            # Receive-section staff, Head, or Admin: any active user except themselves
            rows = db.execute(
                "SELECT u.id,u.name,u.role,u.section_id,s.name as section_name"
                " FROM users u LEFT JOIN sections s ON u.section_id=s.id"
                " WHERE u.active=1 AND u.role!='admin' AND u.id!=?"
                " ORDER BY u.section_id, u.role, u.name",
                (me['id'],)
            ).fetchall()
        result = [dict(r) for r in rows]
        print(f"[recipients] returning {len(result)} users: {[r['name'] for r in result]}")
        return jsonify(result)

@app.route('/api/users', methods=['POST'])
@auth_required
@admin_required
def create_user():
    data = request.json or {}
    name     = data.get('name', '').strip()
    username = data.get('username', '').strip()
    password = data.get('password', '')
    role     = data.get('role')
    section_id = data.get('section_id')
    if not all([name, username, password, role]):
        return jsonify(error='Missing required fields'), 400
    if role in ('head', 'sectional') and not section_id:
        return jsonify(error='Section is required for this role'), 400
    pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    try:
        with get_db() as db:
            cur = db.execute(
                "INSERT INTO users (name,username,password,role,section_id) VALUES (?,?,?,?,?)",
                (name, username, pw, role, section_id or None)
            )
            db.commit()
            return jsonify(id=cur.lastrowid, message='User created')
    except sqlite3.IntegrityError:
        return jsonify(error='Username already exists'), 400

@app.route('/api/users/<int:uid>', methods=['PUT'])
@auth_required
@admin_required
def update_user(uid):
    data = request.json or {}
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (uid,)).fetchone()
        if not user:
            return jsonify(error='User not found'), 404
        pw = bcrypt.hashpw(data['password'].encode(), bcrypt.gensalt()).decode() \
             if data.get('password') else user['password']
        db.execute(
            "UPDATE users SET name=?,username=?,password=?,role=?,section_id=?,active=? WHERE id=?",
            (data.get('name', user['name']),
             data.get('username', user['username']),
             pw,
             data.get('role', user['role']),
             data['section_id'] if 'section_id' in data else user['section_id'],
             data['active'] if 'active' in data else user['active'],
             uid)
        )
        db.commit()
        return jsonify(message='User updated')

@app.route('/api/users/<int:uid>', methods=['DELETE'])
@auth_required
@admin_required
def delete_user(uid):
    with get_db() as db:
        db.execute("UPDATE users SET active=0 WHERE id=?", (uid,))
        db.commit()
        return jsonify(message='User deactivated')

# ── DOCUMENTS ────────────────────────────────────────────────────────────────
@app.route('/api/documents')
@auth_required
def get_documents():
    conditions, params = [], []
    if request.args.get('mine') == 'true':
        conditions.append("d.current_holder_id=?")
        params.append(request.user['id'])
    if request.args.get('section_id'):
        conditions.append("d.current_section_id=?")
        params.append(request.args['section_id'])
    if request.args.get('type'):
        conditions.append("d.doc_type=?")
        params.append(request.args['type'])
    if request.args.get('status'):
        conditions.append("d.status=?")
        params.append(request.args['status'])
    if request.args.get('search'):
        q = f"%{request.args['search']}%"
        conditions.append("(d.doc_number LIKE ? OR d.subject LIKE ? OR d.description LIKE ?)")
        params += [q, q, q]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        SELECT d.*, u.name as holder_name, u.role as holder_role,
               s.name as current_section_name, cu.name as created_by_name
        FROM documents d
        LEFT JOIN users u  ON d.current_holder_id=u.id
        LEFT JOIN sections s  ON d.current_section_id=s.id
        LEFT JOIN users cu ON d.created_by_id=cu.id
        {where} ORDER BY d.created_at DESC
    """
    with get_db() as db:
        docs = [dict(r) for r in db.execute(query, params).fetchall()]
        for doc in docs:
            last = db.execute(
                "SELECT created_at FROM movements WHERE document_id=? ORDER BY id DESC LIMIT 1",
                (doc['id'],)
            ).fetchone()
            doc['days_with_holder'] = days_since(last['created_at'] if last else doc['created_at'])
            doc['days_in_system']   = days_since(doc['received_date'])
        return jsonify(docs)

@app.route('/api/documents/<int:did>')
@auth_required
def get_document(did):
    with get_db() as db:
        doc = db.execute("""
            SELECT d.*, u.name as holder_name, s.name as current_section_name, cu.name as created_by_name
            FROM documents d
            LEFT JOIN users u  ON d.current_holder_id=u.id
            LEFT JOIN sections s ON d.current_section_id=s.id
            LEFT JOIN users cu ON d.created_by_id=cu.id
            WHERE d.id=?
        """, (did,)).fetchone()
        if not doc:
            return jsonify(error='Not found'), 404
        movements = db.execute("""
            SELECT m.*, fu.name as from_name, tu.name as to_name,
                   fs.name as from_section, ts.name as to_section
            FROM movements m
            LEFT JOIN users fu ON m.from_user_id=fu.id
            LEFT JOIN users tu ON m.to_user_id=tu.id
            LEFT JOIN sections fs ON m.from_section_id=fs.id
            LEFT JOIN sections ts ON m.to_section_id=ts.id
            WHERE m.document_id=? ORDER BY m.id ASC
        """, (did,)).fetchall()
        return jsonify(**dict(doc), movements=[dict(m) for m in movements])

@app.route('/api/documents/<int:did>', methods=['PUT'])
@auth_required
@admin_required
def edit_document(did):
    data = request.json or {}
    with get_db() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
        if not doc:
            return jsonify(error='Not found'), 404
        doc_type         = data.get('doc_type',      doc['doc_type'])
        doc_number       = data.get('doc_number',    doc['doc_number']).strip()
        subject          = data.get('subject',       doc['subject']).strip()
        description      = data.get('description',   doc['description'])
        received_date    = data.get('received_date', doc['received_date'])
        ccc_forward_no          = data.get('ccc_forward_no',   doc['ccc_forward_no'])
        ccc_forward_date        = data.get('ccc_forward_date', doc['ccc_forward_date'])
        from_whom               = data.get('from_whom',        doc['from_whom'])
        contractor_consumer_name = data.get('contractor_consumer_name', doc['contractor_consumer_name'])
        status                  = data.get('status',        doc['status'])
        holder_id               = data.get('current_holder_id', doc['current_holder_id'])
        section_id              = data.get('current_section_id', doc['current_section_id'])
        if not all([doc_type, doc_number, subject, received_date]):
            return jsonify(error='Missing required fields'), 400
        db.execute("""
            UPDATE documents SET doc_type=?,doc_number=?,subject=?,description=?,
              received_date=?,ccc_forward_no=?,ccc_forward_date=?,from_whom=?,
              contractor_consumer_name=?,status=?,current_holder_id=?,current_section_id=? WHERE id=?
        """, (doc_type, doc_number, subject, description, received_date,
              ccc_forward_no, ccc_forward_date, from_whom, contractor_consumer_name,
              status, holder_id, section_id, did))
        db.commit()
        return jsonify(message='Document updated')

@app.route('/api/documents/<int:did>', methods=['DELETE'])
@auth_required
@admin_required
def delete_document(did):
    with get_db() as db:
        doc = db.execute("SELECT id FROM documents WHERE id=?", (did,)).fetchone()
        if not doc:
            return jsonify(error='Not found'), 404
        db.execute("DELETE FROM movements WHERE document_id=?", (did,))
        db.execute("DELETE FROM documents WHERE id=?", (did,))
        db.commit()
        return jsonify(message='Document deleted')

@app.route('/api/documents/<int:did>/movements/<int:mid>', methods=['PUT'])
@auth_required
@admin_required
def edit_movement(did, mid):
    data = request.json or {}
    created_at = data.get('created_at', '').strip()
    remarks    = data.get('remarks')
    action     = data.get('action')
    if not created_at:
        return jsonify(error='Date/time required'), 400
    try:
        datetime.strptime(created_at, '%Y-%m-%dT%H:%M')
        created_at = datetime.strptime(created_at, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
    except ValueError:
        try:
            datetime.strptime(created_at, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            return jsonify(error='Invalid date format'), 400
    with get_db() as db:
        m = db.execute("SELECT * FROM movements WHERE id=? AND document_id=?", (mid, did)).fetchone()
        if not m:
            return jsonify(error='Movement not found'), 404
        new_action  = action  if action  in ('Received','Transferred','Forwarded','Routed','Closed') else m['action']
        new_remarks = remarks if remarks is not None else m['remarks']
        db.execute("UPDATE movements SET created_at=?,action=?,remarks=? WHERE id=?",
                   (created_at, new_action, new_remarks, mid))
        db.commit()
        return jsonify(message='Movement updated')

@app.route('/api/documents', methods=['POST'])
@auth_required
def create_document():
    data = request.json or {}
    doc_type         = data.get('doc_type')
    doc_number       = data.get('doc_number', '').strip()
    subject          = data.get('subject', '').strip()
    received_date    = data.get('received_date')
    description      = (data.get('description') or '').strip() or None
    ccc_forward_no   = (data.get('ccc_forward_no') or '').strip() or None
    ccc_forward_date = data.get('ccc_forward_date') or None
    from_whom        = (data.get('from_whom') or '').strip() or None
    contractor_consumer_name = (data.get('contractor_consumer_name') or '').strip() or None
    if not all([doc_type, doc_number, subject, received_date]):
        return jsonify(error='Missing required fields'), 400
    with get_db() as db:
        user = db.execute("SELECT * FROM users WHERE id=?", (request.user['id'],)).fetchone()
        cur = db.execute("""
            INSERT INTO documents
              (doc_type,doc_number,subject,description,received_date,
               ccc_forward_no,ccc_forward_date,from_whom,contractor_consumer_name,
               current_holder_id,current_section_id,created_by_id)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (doc_type, doc_number, subject, description, received_date,
              ccc_forward_no, ccc_forward_date, from_whom, contractor_consumer_name,
              user['id'], user['section_id'], user['id']))
        doc_id = cur.lastrowid
        db.execute("""
            INSERT INTO movements
              (document_id,from_user_id,to_user_id,from_section_id,to_section_id,action,remarks)
            VALUES (?,NULL,?,NULL,?,?,'Initial receipt')
        """, (doc_id, user['id'], user['section_id'], 'Received'))
        db.commit()
        return jsonify(id=doc_id, message='Document received')

@app.route('/api/documents/<int:did>/transfer', methods=['POST'])
@auth_required
def transfer_document(did):
    data       = request.json or {}
    to_user_id = data.get('to_user_id')
    remarks    = (data.get('remarks') or '').strip() or None
    if not to_user_id:
        return jsonify(error='Recipient required'), 400
    with get_db() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
        if not doc:
            return jsonify(error='Document not found'), 404

        requesting_user = db.execute("SELECT * FROM users WHERE id=?", (request.user['id'],)).fetchone()
        to_user         = db.execute("SELECT * FROM users WHERE id=? AND active=1", (to_user_id,)).fetchone()
        if not to_user:
            return jsonify(error='Recipient not found or inactive'), 400

        # Check if requesting user is from the Receive section
        req_sec = db.execute("SELECT name FROM sections WHERE id=?", (requesting_user['section_id'],)).fetchone() \
                  if requesting_user['section_id'] else None
        is_receive_user = req_sec and 'receive' in req_sec['name'].strip().lower()

        # Receive section users can forward ANY document from ANY holder to ANY user
        if is_receive_user:
            from_user = db.execute("SELECT * FROM users WHERE id=?", (doc['current_holder_id'],)).fetchone()
        else:
            # All other users must be the current holder
            if doc['current_holder_id'] != request.user['id']:
                return jsonify(error='You are not the current holder'), 403
            from_user = requesting_user
            # Non-head: can only forward to own section head
            if from_user['role'] == 'sectional':
                head = db.execute(
                    "SELECT id FROM users WHERE section_id=? AND role='head' AND active=1",
                    (from_user['section_id'],)
                ).fetchone()
                if not head or to_user['id'] != head['id']:
                    return jsonify(error='Non-head users can only forward to their Section Head'), 403
            # Head: can forward to same-section users OR other heads/admin
            if from_user['role'] == 'head':
                same_section = (to_user['section_id'] == from_user['section_id'])
                is_head_or_admin = to_user['role'] in ('head', 'admin')
                if not same_section and not is_head_or_admin:
                    return jsonify(error='Section Head can only transfer to same-section users or other Section Heads/Admin'), 403

        action = 'Routed' if is_receive_user else ('Forwarded' if from_user['role'] == 'sectional' else 'Transferred')
        # Use user-supplied forwarding date if provided, else current time
        forwarded_at = data.get('forwarded_at', '').strip()
        if forwarded_at:
            try:
                datetime.strptime(forwarded_at, '%Y-%m-%dT%H:%M')
                forwarded_at = datetime.strptime(forwarded_at, '%Y-%m-%dT%H:%M').strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                forwarded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        else:
            forwarded_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.execute("""
            INSERT INTO movements
              (document_id,from_user_id,to_user_id,from_section_id,to_section_id,action,remarks,created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (did, from_user['id'] if from_user else None, to_user['id'],
              from_user['section_id'] if from_user else None, to_user['section_id'], action, remarks, forwarded_at))
        db.execute(
            "UPDATE documents SET current_holder_id=?,current_section_id=? WHERE id=?",
            (to_user['id'], to_user['section_id'], did)
        )
        db.commit()
        return jsonify(message='Document transferred successfully')

@app.route('/api/documents/<int:did>/status', methods=['PUT'])
@auth_required
def update_status(did):
    status = (request.json or {}).get('status')
    if status not in ('Active', 'Closed', 'Archived'):
        return jsonify(error='Invalid status'), 400
    with get_db() as db:
        doc = db.execute("SELECT * FROM documents WHERE id=?", (did,)).fetchone()
        if not doc:
            return jsonify(error='Not found'), 404
        if request.user['role'] != 'admin' and doc['current_holder_id'] != request.user['id']:
            return jsonify(error='Forbidden'), 403
        db.execute("UPDATE documents SET status=? WHERE id=?", (status, did))
        if status == 'Closed':
            uid = request.user['id']
            u   = db.execute("SELECT section_id FROM users WHERE id=?", (uid,)).fetchone()
            db.execute("""
                INSERT INTO movements
                  (document_id,from_user_id,to_user_id,from_section_id,to_section_id,action,remarks)
                VALUES (?,?,?,?,?,'Closed','Document closed')
            """, (did, uid, uid, u['section_id'], u['section_id']))
        db.commit()
        return jsonify(message='Status updated')

# ── REPORTS ──────────────────────────────────────────────────────────────────
@app.route('/api/reports/holdings')
@auth_required
def holdings():
    with get_db() as db:
        docs = [dict(r) for r in db.execute("""
            SELECT d.*, u.name as holder_name, u.role as holder_role,
                   s.name as current_section_name, cu.name as created_by_name
            FROM documents d
            LEFT JOIN users u  ON d.current_holder_id=u.id
            LEFT JOIN sections s  ON d.current_section_id=s.id
            LEFT JOIN users cu ON d.created_by_id=cu.id
            WHERE d.status='Active'
            ORDER BY d.created_at DESC
        """).fetchall()]
        for doc in docs:
            last = db.execute(
                "SELECT created_at FROM movements WHERE document_id=? ORDER BY id DESC LIMIT 1",
                (doc['id'],)
            ).fetchone()
            doc['days_with_holder'] = days_since(last['created_at'] if last else doc['created_at'])
            doc['days_in_system']   = days_since(doc['received_date'])
        return jsonify(docs)

@app.route('/api/reports/user-activity')
@auth_required
def user_activity():
    with get_db() as db:
        rows = db.execute("""
            SELECT u.id, u.name, u.role, s.name as section_name,
                   COUNT(m.id) as total_movements,
                   SUM(CASE WHEN m.action='Received' THEN 1 ELSE 0 END) as received_count,
                   SUM(CASE WHEN m.action IN ('Transferred','Forwarded','Routed') THEN 1 ELSE 0 END) as forwarded_count,
                   MAX(m.created_at) as last_activity
            FROM users u
            LEFT JOIN sections s ON u.section_id=s.id
            LEFT JOIN movements m ON (m.from_user_id=u.id OR m.to_user_id=u.id)
            WHERE u.active=1 AND u.role != 'admin'
            GROUP BY u.id
            ORDER BY last_activity DESC
        """).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/activity')
@auth_required
def activity_log():
    from_date = request.args.get('from', '')
    to_date   = request.args.get('to', '')
    user_id   = request.args.get('user_id', '')
    conditions = []
    params = []
    if from_date:
        conditions.append("m.created_at >= ?")
        params.append(from_date + ' 00:00:00')
    if to_date:
        conditions.append("m.created_at <= ?")
        params.append(to_date + ' 23:59:59')
    if user_id:
        conditions.append("(m.from_user_id=? OR m.to_user_id=?)")
        params += [user_id, user_id]
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    with get_db() as db:
        rows = db.execute(f"""
            SELECT m.id, m.action, m.remarks, m.created_at,
                   fu.name as from_name, fs.name as from_section,
                   tu.name as to_name,   ts.name as to_section,
                   d.doc_number, d.subject
            FROM movements m
            LEFT JOIN users fu    ON m.from_user_id=fu.id
            LEFT JOIN sections fs ON m.from_section_id=fs.id
            LEFT JOIN users tu    ON m.to_user_id=tu.id
            LEFT JOIN sections ts ON m.to_section_id=ts.id
            LEFT JOIN documents d ON m.document_id=d.id
            {where}
            ORDER BY m.created_at DESC
        """, params).fetchall()
        return jsonify([dict(r) for r in rows])

@app.route('/api/export/documents')
@auth_required
def export_documents():
    import csv, io
    from flask import make_response
    from datetime import datetime as dt

    from_date = request.args.get('from_date', '')
    to_date   = request.args.get('to_date', '')
    doc_types = request.args.getlist('doc_type')   # e.g. ['Notesheet','Bill']
    status    = request.args.get('status', '')      # Active / Closed / ''

    conditions = []
    params     = []

    if from_date:
        conditions.append("date(d.received_date) >= date(?)")
        params.append(from_date)
    if to_date:
        conditions.append("date(d.received_date) <= date(?)")
        params.append(to_date)
    if doc_types:
        placeholders = ','.join('?' * len(doc_types))
        conditions.append(f"d.doc_type IN ({placeholders})")
        params.extend(doc_types)
    if status:
        conditions.append("d.status = ?")
        params.append(status)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    with get_db() as db:
        rows = db.execute(f"""
            SELECT
                d.id,
                d.doc_type,
                d.doc_number,
                d.subject,
                d.status,
                d.received_date,
                d.ccc_forward_no,
                d.ccc_forward_date,
                d.from_whom,
                d.contractor_consumer_name AS contractor_name,
                d.description,
                d.created_at,
                cu.name  AS current_holder,
                cs.name  AS current_section,
                ru.name  AS received_by,
                (SELECT COUNT(*) FROM movements m WHERE m.document_id = d.id) AS total_transfers,
                (SELECT MAX(m.created_at) FROM movements m WHERE m.document_id = d.id) AS last_moved_at,
                CAST(julianday('now') - julianday(d.received_date) AS INTEGER) AS days_pending
            FROM documents d
            LEFT JOIN users    cu ON d.current_holder_id  = cu.id
            LEFT JOIN sections cs ON d.current_section_id = cs.id
            LEFT JOIN users    ru ON d.created_by_id      = ru.id
            {where}
            ORDER BY d.received_date DESC, d.id DESC
        """, params).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        'Sr No', 'Document Type', 'Document Number', 'Subject', 'Status',
        'Received Date', 'CCC Forward No', 'CCC Forward Date',
        'From Whom Received', 'Contractor / Consumer Name',
        'Received By', 'Current Holder', 'Current Section',
        'Days Pending', 'Total Transfers', 'Last Movement',
        'Description', 'Entry Created At'
    ])
    for i, r in enumerate(rows, 1):
        writer.writerow([
            i,
            r['doc_type']         or '',
            r['doc_number']       or '',
            r['subject']          or '',
            r['status']           or '',
            r['received_date']    or '',
            r['ccc_forward_no']   or '',
            r['ccc_forward_date'] or '',
            r['from_whom']        or '',
            r['contractor_name']  or '',
            r['received_by']      or '',
            r['current_holder']   or '',
            r['current_section']  or '',
            r['days_pending']     or 0,
            r['total_transfers']  or 0,
            r['last_moved_at']    or '',
            r['description']      or '',
            r['created_at']       or '',
        ])

    csv_data = output.getvalue()
    fname = 'WBSEDCL_Export_' + dt.now().strftime('%Y%m%d_%H%M%S') + '.csv'
    response = make_response(csv_data)
    response.headers['Content-Type']        = 'text/csv; charset=utf-8'
    response.headers['Content-Disposition'] = 'attachment; filename="' + fname + '"'
    return response


@app.route('/api/admin/backup')
@auth_required
@admin_required
def backup_db():
    import io, tempfile, os
    from flask import send_file, make_response
    try:
        # Backup into an in-memory SQLite DB, then write to BytesIO
        buf = io.BytesIO()
        tmp_path = tempfile.mktemp(suffix='.db')
        src = sqlite3.connect(DB_FILE)
        dst = sqlite3.connect(tmp_path)
        src.backup(dst)
        src.close()
        dst.close()
        with open(tmp_path, 'rb') as f:
            buf.write(f.read())
        os.unlink(tmp_path)
        buf.seek(0)
        filename = 'wbsedcl_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.db'
        response = make_response(buf.read())
        response.headers['Content-Type'] = 'application/octet-stream'
        response.headers['Content-Disposition'] = 'attachment; filename="' + filename + '"'
        return response
    except Exception as e:
        return jsonify(error=str(e)), 500

# -- ENTRY POINT -------------------------------------------------------------
def _show_error(title, msg):
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, str(msg), str(title), 0x10)
    except Exception:
        print('ERROR: ' + str(title) + ' - ' + str(msg))
        input('Press Enter to exit...')

if __name__ == '__main__':
    import threading, webbrowser, time

    try:
        migrate_db()
        init_db()
    except Exception as e:
        _show_error('WBSEDCL - DB Error', 'Cannot initialise database. ' + str(e))
        import sys; sys.exit(1)

    def _open_browser():
        time.sleep(2.0)
        webbrowser.open('http://localhost:3000')

    threading.Thread(target=_open_browser, daemon=True).start()

    print('=' * 50)
    print('  WBSEDCL Receive Section')
    print('  Server: http://localhost:3000')
    print('  Login:  admin / admin123')
    print('  Ctrl+C to stop')
    print('=' * 50)

    try:
        app.run(host='0.0.0.0', port=3000, debug=False, use_reloader=False)
    except OSError as e:
        msg = str(e)
        if 'Address already in use' in msg or '10048' in msg:
            _show_error('WBSEDCL - Port Busy',
                        'Port 3000 is already in use. '
                        'The app may already be running. '
                        'Open http://localhost:3000 in your browser.')
        else:
            _show_error('WBSEDCL - Network Error', msg)
        import sys; sys.exit(1)
    except Exception as e:
        _show_error('WBSEDCL - Error', str(e))
        import sys; sys.exit(1)
