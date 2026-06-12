// WBSEDCL Receive Section - Backend Server
// Run: node server.js

const express = require('express');
const Database = require('better-sqlite3');
const bcrypt = require('bcryptjs');
const jwt = require('jsonwebtoken');
const path = require('path');

const app = express();
const PORT = 3000;
const JWT_SECRET = 'wbsedcl-receive-secret-2024';

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

// ─── DATABASE SETUP ───────────────────────────────────────────────────────────
const db = new Database('wbsedcl.db');
db.pragma('journal_mode = WAL');
db.pragma('foreign_keys = ON');

db.exec(`
  CREATE TABLE IF NOT EXISTS sections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
  );

  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL UNIQUE,
    password TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('admin','head','sectional')),
    section_id INTEGER REFERENCES sections(id),
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
  );

  CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    doc_type TEXT NOT NULL CHECK(doc_type IN ('Notesheet','Bill','Letter')),
    doc_number TEXT NOT NULL,
    subject TEXT NOT NULL,
    description TEXT,
    received_date TEXT NOT NULL,
    current_holder_id INTEGER REFERENCES users(id),
    current_section_id INTEGER REFERENCES sections(id),
    status TEXT NOT NULL DEFAULT 'Active' CHECK(status IN ('Active','Closed','Archived')),
    created_by_id INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
  );

  CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    from_user_id INTEGER REFERENCES users(id),
    to_user_id INTEGER NOT NULL REFERENCES users(id),
    from_section_id INTEGER REFERENCES sections(id),
    to_section_id INTEGER REFERENCES sections(id),
    action TEXT NOT NULL CHECK(action IN ('Received','Transferred','Forwarded','Closed')),
    remarks TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime'))
  );
`);

// Seed initial data if empty
const sectionCount = db.prepare('SELECT COUNT(*) as c FROM sections').get().c;
if (sectionCount === 0) {
  const insertSection = db.prepare('INSERT INTO sections (name) VALUES (?)');
  ['HR Section','Account Section','DCC Section','DM Section','Divisional Store Section'].forEach(s => insertSection.run(s));

  const hash = bcrypt.hashSync('admin123', 10);
  db.prepare(`INSERT INTO users (name, username, password, role, section_id, active)
              VALUES ('Administrator', 'admin', ?, 'admin', NULL, 1)`).run(hash);
  console.log('✓ Default admin created: username=admin, password=admin123');
}

// ─── AUTH MIDDLEWARE ──────────────────────────────────────────────────────────
function auth(req, res, next) {
  const token = req.headers.authorization?.split(' ')[1];
  if (!token) return res.status(401).json({ error: 'Unauthorized' });
  try {
    req.user = jwt.verify(token, JWT_SECRET);
    next();
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}

function adminOnly(req, res, next) {
  if (req.user.role !== 'admin') return res.status(403).json({ error: 'Admin only' });
  next();
}

// ─── AUTH ROUTES ──────────────────────────────────────────────────────────────
app.post('/api/auth/login', (req, res) => {
  const { username, password } = req.body;
  const user = db.prepare('SELECT * FROM users WHERE username = ? AND active = 1').get(username);
  if (!user || !bcrypt.compareSync(password, user.password))
    return res.status(401).json({ error: 'Invalid credentials' });

  const section = user.section_id
    ? db.prepare('SELECT name FROM sections WHERE id = ?').get(user.section_id)
    : null;

  const token = jwt.sign(
    { id: user.id, username: user.username, name: user.name, role: user.role, section_id: user.section_id, section_name: section?.name || null },
    JWT_SECRET, { expiresIn: '12h' }
  );
  res.json({ token, user: { id: user.id, name: user.name, username: user.username, role: user.role, section_id: user.section_id, section_name: section?.name } });
});

app.get('/api/auth/me', auth, (req, res) => {
  const user = db.prepare('SELECT id,name,username,role,section_id,active,created_at FROM users WHERE id=?').get(req.user.id);
  const section = user.section_id ? db.prepare('SELECT name FROM sections WHERE id=?').get(user.section_id) : null;
  res.json({ ...user, section_name: section?.name });
});

// ─── SECTIONS ────────────────────────────────────────────────────────────────
app.get('/api/sections', auth, (req, res) => {
  res.json(db.prepare('SELECT * FROM sections ORDER BY id').all());
});

// ─── USERS (Admin) ───────────────────────────────────────────────────────────
app.get('/api/users', auth, (req, res) => {
  const rows = db.prepare(`
    SELECT u.id, u.name, u.username, u.role, u.section_id, u.active, u.created_at, s.name as section_name
    FROM users u LEFT JOIN sections s ON u.section_id = s.id
    ORDER BY u.id
  `).all();
  res.json(rows);
});

app.get('/api/users/heads', auth, (req, res) => {
  const rows = db.prepare(`
    SELECT u.id, u.name, u.role, u.section_id, s.name as section_name
    FROM users u LEFT JOIN sections s ON u.section_id = s.id
    WHERE u.role IN ('admin','head') AND u.active = 1
    ORDER BY u.name
  `).all();
  res.json(rows);
});

app.post('/api/users', auth, adminOnly, (req, res) => {
  const { name, username, password, role, section_id } = req.body;
  if (!name || !username || !password || !role) return res.status(400).json({ error: 'Missing fields' });
  if (['head','sectional'].includes(role) && !section_id) return res.status(400).json({ error: 'Section required' });
  try {
    const hash = bcrypt.hashSync(password, 10);
    const result = db.prepare('INSERT INTO users (name,username,password,role,section_id) VALUES (?,?,?,?,?)').run(name, username, hash, role, section_id || null);
    res.json({ id: result.lastInsertRowid, message: 'User created' });
  } catch (e) {
    if (e.message.includes('UNIQUE')) return res.status(400).json({ error: 'Username already exists' });
    res.status(500).json({ error: e.message });
  }
});

app.put('/api/users/:id', auth, adminOnly, (req, res) => {
  const { name, username, password, role, section_id, active } = req.body;
  const user = db.prepare('SELECT * FROM users WHERE id=?').get(req.params.id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  const hash = password ? bcrypt.hashSync(password, 10) : user.password;
  db.prepare('UPDATE users SET name=?,username=?,password=?,role=?,section_id=?,active=? WHERE id=?')
    .run(name||user.name, username||user.username, hash, role||user.role, section_id !== undefined ? section_id : user.section_id, active !== undefined ? active : user.active, req.params.id);
  res.json({ message: 'User updated' });
});

app.delete('/api/users/:id', auth, adminOnly, (req, res) => {
  db.prepare('UPDATE users SET active=0 WHERE id=?').run(req.params.id);
  res.json({ message: 'User deactivated' });
});

// ─── DOCUMENTS ────────────────────────────────────────────────────────────────
app.get('/api/documents', auth, (req, res) => {
  let query = `
    SELECT d.*,
           u.name as holder_name, u.role as holder_role,
           s.name as current_section_name,
           cu.name as created_by_name
    FROM documents d
    LEFT JOIN users u ON d.current_holder_id = u.id
    LEFT JOIN sections s ON d.current_section_id = s.id
    LEFT JOIN users cu ON d.created_by_id = cu.id
  `;
  const conditions = [];
  const params = [];

  if (req.query.mine === 'true') {
    conditions.push('d.current_holder_id = ?');
    params.push(req.user.id);
  }
  if (req.query.section_id) {
    conditions.push('d.current_section_id = ?');
    params.push(req.query.section_id);
  }
  if (req.query.type) {
    conditions.push('d.doc_type = ?');
    params.push(req.query.type);
  }
  if (req.query.status) {
    conditions.push('d.status = ?');
    params.push(req.query.status);
  }
  if (req.query.search) {
    conditions.push('(d.doc_number LIKE ? OR d.subject LIKE ? OR d.description LIKE ?)');
    const q = `%${req.query.search}%`;
    params.push(q, q, q);
  }
  if (conditions.length) query += ' WHERE ' + conditions.join(' AND ');
  query += ' ORDER BY d.created_at DESC';

  const docs = db.prepare(query).all(...params);

  // Add days_held for each doc
  const now = new Date();
  docs.forEach(doc => {
    const created = new Date(doc.created_at);
    doc.days_in_system = Math.floor((now - created) / 86400000);

    // Get last movement time for this holder
    const lastMove = db.prepare(`
      SELECT created_at FROM movements WHERE document_id=? ORDER BY id DESC LIMIT 1
    `).get(doc.id);
    if (lastMove) {
      const moved = new Date(lastMove.created_at);
      doc.days_with_holder = Math.floor((now - moved) / 86400000);
    } else {
      doc.days_with_holder = doc.days_in_system;
    }
  });

  res.json(docs);
});

app.get('/api/documents/:id', auth, (req, res) => {
  const doc = db.prepare(`
    SELECT d.*, u.name as holder_name, s.name as current_section_name, cu.name as created_by_name
    FROM documents d
    LEFT JOIN users u ON d.current_holder_id = u.id
    LEFT JOIN sections s ON d.current_section_id = s.id
    LEFT JOIN users cu ON d.created_by_id = cu.id
    WHERE d.id=?
  `).get(req.params.id);
  if (!doc) return res.status(404).json({ error: 'Not found' });

  const movements = db.prepare(`
    SELECT m.*,
           fu.name as from_name, tu.name as to_name,
           fs.name as from_section, ts.name as to_section
    FROM movements m
    LEFT JOIN users fu ON m.from_user_id = fu.id
    LEFT JOIN users tu ON m.to_user_id = tu.id
    LEFT JOIN sections fs ON m.from_section_id = fs.id
    LEFT JOIN sections ts ON m.to_section_id = ts.id
    WHERE m.document_id=? ORDER BY m.id ASC
  `).all(req.params.id);

  res.json({ ...doc, movements });
});

app.post('/api/documents', auth, (req, res) => {
  const { doc_type, doc_number, subject, description, received_date } = req.body;
  if (!doc_type || !doc_number || !subject || !received_date)
    return res.status(400).json({ error: 'Missing required fields' });

  const user = db.prepare('SELECT * FROM users WHERE id=?').get(req.user.id);
  const result = db.prepare(`
    INSERT INTO documents (doc_type, doc_number, subject, description, received_date, current_holder_id, current_section_id, created_by_id)
    VALUES (?,?,?,?,?,?,?,?)
  `).run(doc_type, doc_number, subject, description || null, received_date, user.id, user.section_id || null, user.id);

  // Log initial movement
  db.prepare(`
    INSERT INTO movements (document_id, from_user_id, to_user_id, from_section_id, to_section_id, action, remarks)
    VALUES (?,NULL,?,NULL,?,?,'Initial receipt')
  `).run(result.lastInsertRowid, user.id, user.section_id || null, 'Received');

  res.json({ id: result.lastInsertRowid, message: 'Document received' });
});

app.post('/api/documents/:id/transfer', auth, (req, res) => {
  const { to_user_id, remarks } = req.body;
  if (!to_user_id) return res.status(400).json({ error: 'Recipient required' });

  const doc = db.prepare('SELECT * FROM documents WHERE id=?').get(req.params.id);
  if (!doc) return res.status(404).json({ error: 'Document not found' });
  if (doc.current_holder_id !== req.user.id) return res.status(403).json({ error: 'You are not the current holder' });

  const fromUser = db.prepare('SELECT * FROM users WHERE id=?').get(req.user.id);
  const toUser = db.prepare('SELECT * FROM users WHERE id=?').get(to_user_id);
  if (!toUser || !toUser.active) return res.status(400).json({ error: 'Recipient not found or inactive' });

  // Role-based transfer rules
  // sectional -> can only transfer to their own section head
  if (fromUser.role === 'sectional') {
    const sectionHead = db.prepare('SELECT id FROM users WHERE section_id=? AND role=? AND active=1').get(fromUser.section_id, 'head');
    if (!sectionHead || toUser.id !== sectionHead.id)
      return res.status(403).json({ error: 'Sectional users can only forward to their Section Head' });
  }
  // head -> can transfer to any head or admin
  if (fromUser.role === 'head') {
    if (!['head','admin'].includes(toUser.role))
      return res.status(403).json({ error: 'Section Heads can only transfer to other Section Heads or Admin' });
  }

  const action = fromUser.role === 'sectional' ? 'Forwarded' : 'Transferred';

  db.prepare(`
    INSERT INTO movements (document_id, from_user_id, to_user_id, from_section_id, to_section_id, action, remarks)
    VALUES (?,?,?,?,?,?,?)
  `).run(doc.id, fromUser.id, toUser.id, fromUser.section_id, toUser.section_id, action, remarks || null);

  db.prepare('UPDATE documents SET current_holder_id=?, current_section_id=? WHERE id=?')
    .run(toUser.id, toUser.section_id, doc.id);

  res.json({ message: 'Document transferred successfully' });
});

app.put('/api/documents/:id/status', auth, (req, res) => {
  const { status } = req.body;
  if (!['Active','Closed','Archived'].includes(status)) return res.status(400).json({ error: 'Invalid status' });
  const doc = db.prepare('SELECT * FROM documents WHERE id=?').get(req.params.id);
  if (!doc) return res.status(404).json({ error: 'Not found' });
  if (req.user.role !== 'admin' && doc.current_holder_id !== req.user.id)
    return res.status(403).json({ error: 'Forbidden' });
  db.prepare('UPDATE documents SET status=? WHERE id=?').run(status, req.params.id);
  if (status === 'Closed') {
    db.prepare(`INSERT INTO movements (document_id,from_user_id,to_user_id,from_section_id,to_section_id,action,remarks)
                VALUES (?,?,?,?,?,?,?)`).run(doc.id, req.user.id, req.user.id, db.prepare('SELECT * FROM users WHERE id=?').get(req.user.id).section_id, db.prepare('SELECT * FROM users WHERE id=?').get(req.user.id).section_id, 'Closed', 'Document closed');
  }
  res.json({ message: 'Status updated' });
});

// ─── REPORTS ─────────────────────────────────────────────────────────────────
app.get('/api/reports/holdings', auth, (req, res) => {
  // For each active document: who holds it, how long, trail
  const docs = db.prepare(`
    SELECT d.id, d.doc_type, d.doc_number, d.subject, d.status, d.received_date, d.created_at,
           u.name as holder_name, u.role as holder_role, u.id as holder_id,
           s.name as section_name
    FROM documents d
    LEFT JOIN users u ON d.current_holder_id = u.id
    LEFT JOIN sections s ON d.current_section_id = s.id
    WHERE d.status = 'Active'
    ORDER BY d.created_at ASC
  `).all();

  const now = new Date();
  const result = docs.map(doc => {
    const lastMove = db.prepare(`
      SELECT created_at FROM movements WHERE document_id=? ORDER BY id DESC LIMIT 1
    `).get(doc.id);
    const since = lastMove ? new Date(lastMove.created_at) : new Date(doc.created_at);
    return {
      ...doc,
      days_with_holder: Math.floor((now - since) / 86400000),
      days_in_system: Math.floor((now - new Date(doc.created_at)) / 86400000)
    };
  });

  res.json(result);
});

app.get('/api/reports/user-activity', auth, adminOnly, (req, res) => {
  const { from, to, user_id } = req.query;
  let cond = '';
  const params = [];
  if (from) { cond += ' AND m.created_at >= ?'; params.push(from); }
  if (to) { cond += ' AND m.created_at <= ?'; params.push(to + ' 23:59:59'); }
  if (user_id) { cond += ' AND (m.from_user_id=? OR m.to_user_id=?)'; params.push(user_id, user_id); }

  const movements = db.prepare(`
    SELECT m.*, d.doc_type, d.doc_number, d.subject,
           fu.name as from_name, tu.name as to_name,
           fs.name as from_section, ts.name as to_section
    FROM movements m
    JOIN documents d ON m.document_id = d.id
    LEFT JOIN users fu ON m.from_user_id = fu.id
    LEFT JOIN users tu ON m.to_user_id = tu.id
    LEFT JOIN sections fs ON m.from_section_id = fs.id
    LEFT JOIN sections ts ON m.to_section_id = ts.id
    WHERE 1=1 ${cond}
    ORDER BY m.created_at DESC
    LIMIT 500
  `).all(...params);

  res.json(movements);
});

// ─── START ────────────────────────────────────────────────────────────────────
app.listen(PORT, () => {
  console.log(`\n✅ WBSEDCL Receive Section running at http://localhost:${PORT}`);
  console.log(`   Default login: admin / admin123\n`);
});
