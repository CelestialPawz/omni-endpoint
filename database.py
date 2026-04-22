import aiosqlite
import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/data/omni.db")

_SCHEMA = """
    CREATE TABLE IF NOT EXISTS warnings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        moderator_id TEXT NOT NULL,
        reason TEXT DEFAULT 'No reason provided',
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS tags (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        name TEXT NOT NULL,
        content TEXT NOT NULL,
        created_by TEXT,
        uses INTEGER DEFAULT 0,
        UNIQUE(guild_id, name)
    );
    CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        channel_id TEXT NOT NULL,
        message TEXT NOT NULL,
        due_at REAL NOT NULL,
        done INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS starboard_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        message_id TEXT NOT NULL,
        starboard_message_id TEXT,
        star_count INTEGER DEFAULT 0,
        UNIQUE(guild_id, message_id)
    );
    CREATE TABLE IF NOT EXISTS guild_settings (
        guild_id TEXT PRIMARY KEY,
        starboard_channel_id TEXT DEFAULT NULL,
        starboard_threshold INTEGER DEFAULT 3,
        automod_spam INTEGER DEFAULT 1,
        automod_caps INTEGER DEFAULT 1,
        automod_invites INTEGER DEFAULT 1,
        automod_spam_threshold INTEGER DEFAULT 5,
        automod_caps_ratio REAL DEFAULT 0.7,
        log_channel_id TEXT DEFAULT NULL,
        welcome_channel_id TEXT DEFAULT NULL,
        welcome_message TEXT DEFAULT 'Welcome {user} to {server}!',
        auto_role_id TEXT DEFAULT NULL
    );
    CREATE TABLE IF NOT EXISTS mod_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        action TEXT NOT NULL,
        moderator_id TEXT NOT NULL,
        target_id TEXT,
        reason TEXT,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS mod_notes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        moderator_id TEXT NOT NULL,
        note TEXT NOT NULL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS levels (
        guild_id TEXT NOT NULL,
        user_id TEXT NOT NULL,
        xp INTEGER DEFAULT 0,
        level INTEGER DEFAULT 0,
        last_xp_time REAL DEFAULT 0,
        PRIMARY KEY (guild_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS level_roles (
        guild_id TEXT NOT NULL,
        level_required INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (guild_id, level_required)
    );
    CREATE TABLE IF NOT EXISTS modmail_sessions (
        user_id TEXT PRIMARY KEY,
        thread_id INTEGER NOT NULL,
        closed INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS ban_appeals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        discord_username TEXT NOT NULL,
        discord_id TEXT NOT NULL,
        ban_reason TEXT,
        appeal_message TEXT NOT NULL,
        status TEXT DEFAULT 'pending',
        channel_id INTEGER,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS music_queue (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        position INTEGER NOT NULL,
        track_title TEXT NOT NULL,
        track_url TEXT NOT NULL,
        duration INTEGER,
        added_by TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS music_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        track_title TEXT NOT NULL,
        track_url TEXT NOT NULL,
        duration INTEGER,
        played_by TEXT,
        played_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS music_favorites (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        track_title TEXT NOT NULL,
        track_url TEXT NOT NULL,
        uploader TEXT,
        thumbnail TEXT,
        added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, track_url)
    );
    CREATE TABLE IF NOT EXISTS music_playlists (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        name TEXT NOT NULL,
        is_public INTEGER DEFAULT 0,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(user_id, name)
    );
    CREATE TABLE IF NOT EXISTS music_playlist_tracks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        playlist_id INTEGER NOT NULL,
        position INTEGER NOT NULL,
        track_title TEXT NOT NULL,
        track_url TEXT NOT NULL,
        duration INTEGER,
        FOREIGN KEY (playlist_id) REFERENCES music_playlists(id) ON DELETE CASCADE
    );
"""

async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(_SCHEMA)
        for stmt in [
            "ALTER TABLE tags ADD COLUMN uses INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(stmt)
            except Exception:
                pass
        await db.commit()

def init_db_sync():
    """Synchronous DB init for Flask web panel."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.executescript(_SCHEMA)
    for stmt in [
        "ALTER TABLE tags ADD COLUMN uses INTEGER DEFAULT 0",
    ]:
        try:
            conn.execute(stmt)
        except Exception:
            pass
    conn.commit()
    conn.close()

async def get_setting(guild_id: str, key: str, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute(f"SELECT {key} FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
        except Exception:
            return default

async def set_setting(guild_id: str, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT INTO guild_settings (guild_id, {key}) VALUES (?, ?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {key} = excluded.{key}",
            (guild_id, value)
        )
        await db.commit()

async def add_mod_log(guild_id: str, action: str, moderator_id: str, target_id: str = None, reason: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mod_logs (guild_id, action, moderator_id, target_id, reason) VALUES (?, ?, ?, ?, ?)",
            (guild_id, action, moderator_id, target_id, reason)
        )
        await db.commit()

# ── Music Functions ──────────────────────────────────────────────────────

async def save_queue(guild_id: str, queue_list: list):
    """Save queue to database. Format: [(title, url, duration), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM music_queue WHERE guild_id = ?", (guild_id,))
        for pos, (title, url, duration) in enumerate(queue_list):
            await db.execute(
                "INSERT INTO music_queue (guild_id, position, track_title, track_url, duration) VALUES (?, ?, ?, ?, ?)",
                (guild_id, pos, title, url, duration)
            )
        await db.commit()

async def load_queue(guild_id: str) -> list:
    """Load queue from database. Returns: [(title, url, duration), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, duration FROM music_queue WHERE guild_id = ? ORDER BY position",
            (guild_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [(row[0], row[1], row[2]) for row in rows]

async def add_to_history(guild_id: str, title: str, url: str, duration: int, user_id: str):
    """Log a played track to history."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO music_history (guild_id, track_title, track_url, duration, played_by) VALUES (?, ?, ?, ?, ?)",
            (guild_id, title, url, duration, user_id)
        )
        await db.commit()

async def add_favorite(user_id: str, title: str, url: str, uploader: str = None, thumbnail: str = None):
    """Add track to user favorites."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            await db.execute(
                "INSERT INTO music_favorites (user_id, track_title, track_url, uploader, thumbnail) VALUES (?, ?, ?, ?, ?)",
                (user_id, title, url, uploader, thumbnail)
            )
        except Exception:
            pass
        await db.commit()

async def get_favorites(user_id: str, limit: int = 50) -> list:
    """Get user's favorite tracks."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, uploader, thumbnail FROM music_favorites WHERE user_id = ? ORDER BY added_at DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()

async def create_playlist(user_id: str, name: str, is_public: bool = False) -> int:
    """Create a playlist, return playlist ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO music_playlists (user_id, name, is_public) VALUES (?, ?, ?)",
            (user_id, name, 1 if is_public else 0)
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            return (await cur.fetchone())[0]

async def add_to_playlist(playlist_id: int, title: str, url: str, duration: int):
    """Add track to playlist."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT MAX(position) FROM music_playlist_tracks WHERE playlist_id = ?",
            (playlist_id,)
        ) as cur:
            max_pos = (await cur.fetchone())[0]
        position = (max_pos or -1) + 1
        await db.execute(
            "INSERT INTO music_playlist_tracks (playlist_id, position, track_title, track_url, duration) VALUES (?, ?, ?, ?, ?)",
            (playlist_id, position, title, url, duration)
        )
        await db.commit()

async def get_playlist(playlist_id: int) -> list:
    """Get playlist tracks."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, duration FROM music_playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,)
        ) as cur:
            return await cur.fetchall()
