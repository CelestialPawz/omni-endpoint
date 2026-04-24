Summary: Analytics DB migration for omni-endpoint
Date: 2026-04-23

What was done:
- Added `commands` and `command_usage` tables to database.py _SCHEMA to support the web analytics dashboard.
- Committed change: commit dad1678cf761a768d4eca4ea325fd97dde593577 (pushed to origin/main).

Why:
- The web panel errored: "no such table: command_usage". Adding schema ensures new containers start with required tables.

How to apply immediately on server:
1) Create tables inside running containers (if docker present):
   docker exec -i omni-web sqlite3 /data/omni.db "CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,name TEXT NOT NULL,description TEXT,UNIQUE(guild_id,name)); CREATE TABLE IF NOT EXISTS command_usage (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,command_id INTEGER,user_id TEXT,date TEXT NOT NULL,uses INTEGER DEFAULT 1,FOREIGN KEY(command_id) REFERENCES commands(id));"
   docker restart omni-web
   docker exec -i omni-bot sqlite3 /data/omni.db "CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,name TEXT NOT NULL,description TEXT,UNIQUE(guild_id,name)); CREATE TABLE IF NOT EXISTS command_usage (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,command_id INTEGER,user_id TEXT,date TEXT NOT NULL,uses INTEGER DEFAULT 1,FOREIGN KEY(command_id) REFERENCES commands(id));"
   docker restart omni-bot

2) If sqlite3 not available in containers, run via python inside container (repeat per container):
   docker exec -i omni-web python - <<'PY'
import sqlite3
c=sqlite3.connect('/data/omni.db')
c.executescript('''CREATE TABLE IF NOT EXISTS commands (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,name TEXT NOT NULL,description TEXT,UNIQUE(guild_id,name));
CREATE TABLE IF NOT EXISTS command_usage (id INTEGER PRIMARY KEY AUTOINCREMENT,guild_id TEXT NOT NULL,command_id INTEGER,user_id TEXT,date TEXT NOT NULL,uses INTEGER DEFAULT 1,FOREIGN KEY(command_id) REFERENCES commands(id));''')
c.commit(); c.close()
PY

Verification (run on server):
- docker exec -i omni-web sqlite3 /data/omni.db "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('commands','command_usage');"
- docker logs --tail 200 omni-web   # check for analytics errors

Notes:
- database.init_db/init_db_sync will create these tables on startup for new installs.
- This file records the chat actions and commands to re-run manually.

Commit: dad1678cf761a768d4eca4ea325fd97dde593577
Repo: https://github.com/CelestialPawz/omni-endpoint

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
