CREATE TABLE IF NOT EXISTS loop_sessions(id TEXT PRIMARY KEY,created_at TEXT,state TEXT);
CREATE TABLE IF NOT EXISTS loop_iterations(session_id TEXT,iteration INTEGER,run_id TEXT,status TEXT,PRIMARY KEY(session_id,iteration));
