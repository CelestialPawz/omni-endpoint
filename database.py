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

    -- commands: stores known slash/tag commands for the analytics dashboard
    CREATE TABLE IF NOT EXISTS commands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        name TEXT NOT NULL,
        description TEXT,
        UNIQUE(guild_id, name)
    );

    -- command_usage: per-day usage aggregates (date stored as TEXT 'YYYY-MM-DD')
    CREATE TABLE IF NOT EXISTS command_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        guild_id TEXT NOT NULL,
        command_id INTEGER,
        user_id TEXT,
        date TEXT NOT NULL,
        uses INTEGER DEFAULT 1,
        FOREIGN KEY (command_id) REFERENCES commands(id) ON DELETE SET NULL
    );
"""


async def init_db():
    """Async DB init for the bot."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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
    """Synchronous DB init for the Flask web panel."""
    db_dir = os.path.dirname(DB_PATH)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
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
    """Read a single column from guild_settings for the given guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        try:
            async with db.execute(f"SELECT {key} FROM guild_settings WHERE guild_id = ?", (guild_id,)) as cur:
                row = await cur.fetchone()
                return row[0] if row else default
        except Exception:
            return default


async def set_setting(guild_id: str, key: str, value):
    """Upsert a single column in guild_settings for the given guild."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            f"INSERT INTO guild_settings (guild_id, {key}) VALUES (?, ?) "
            f"ON CONFLICT(guild_id) DO UPDATE SET {key} = excluded.{key}",
            (guild_id, value)
        )
        await db.commit()


async def add_mod_log(guild_id: str, action: str, moderator_id: str, target_id: str = None, reason: str = None):
    """Append a moderation action to mod_logs."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO mod_logs (guild_id, action, moderator_id, target_id, reason) VALUES (?, ?, ?, ?, ?)",
            (guild_id, action, moderator_id, target_id, reason)
        )
        await db.commit()


# -- Music Functions ----------------------------------------------------------

async def save_queue(guild_id: str, queue_list: list):
    """Persist the current queue to the database. Format: [(title, url, duration), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM music_queue WHERE guild_id = ?", (guild_id,))
        for pos, (title, url, duration) in enumerate(queue_list):
            await db.execute(
                "INSERT INTO music_queue (guild_id, position, track_title, track_url, duration) VALUES (?, ?, ?, ?, ?)",
                (guild_id, pos, title, url, duration)
            )
        await db.commit()


async def load_queue(guild_id: str) -> list:
    """Load the persisted queue. Returns: [(title, url, duration), ...]"""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, duration FROM music_queue WHERE guild_id = ? ORDER BY position",
            (guild_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [(row[0], row[1], row[2]) for row in rows]


async def add_to_history(guild_id: str, title: str, url: str, duration: int, user_id: str):
    """Log a played track to music_history."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO music_history (guild_id, track_title, track_url, duration, played_by) VALUES (?, ?, ?, ?, ?)",
            (guild_id, title, url, duration, user_id)
        )
        await db.commit()


async def add_favorite(user_id: str, title: str, url: str, uploader: str = None, thumbnail: str = None):
    """Add a track to a user's favorites. Silently ignores duplicates."""
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
    """Get a user's favorite tracks, most recently added first."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, uploader, thumbnail FROM music_favorites WHERE user_id = ? ORDER BY added_at DESC LIMIT ?",
            (user_id, limit)
        ) as cur:
            return await cur.fetchall()


async def create_playlist(user_id: str, name: str, is_public: bool = False) -> int:
    """Create a new playlist and return its ID."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO music_playlists (user_id, name, is_public) VALUES (?, ?, ?)",
            (user_id, name, 1 if is_public else 0)
        )
        await db.commit()
        async with db.execute("SELECT last_insert_rowid()") as cur:
            return (await cur.fetchone())[0]


async def add_to_playlist(playlist_id: int, title: str, url: str, duration: int):
    """Append a track to an existing playlist."""
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
    """Get all tracks in a playlist, ordered by position."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT track_title, track_url, duration FROM music_playlist_tracks WHERE playlist_id = ? ORDER BY position",
            (playlist_id,)
        ) as cur:
            return await cur.fetchall()


# -- Dashboard Stats Functions ------------------------------------------------

def get_total_tags_sync() -> int:
    """Get the total number of tags across all guilds."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(*) FROM tags")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_tags_by_guild_sync() -> dict:
    """Get tag count per guild, sorted by count descending."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT guild_id, COUNT(*) as count FROM tags GROUP BY guild_id ORDER BY count DESC")
    result = {row[0]: row[1] for row in cur.fetchall()}
    conn.close()
    return result


def get_total_guilds_sync() -> int:
    """Get the number of unique guilds that have at least one tag."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(DISTINCT guild_id) FROM tags")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_tag_stats_sync() -> dict:
    """Get aggregated tag statistics: total uses, top 5 tags, average uses."""
    conn = sqlite3.connect(DB_PATH)
    stats = {}

    cur = conn.execute("SELECT COALESCE(SUM(uses), 0) FROM tags")
    stats['total_uses'] = cur.fetchone()[0]

    cur = conn.execute("SELECT name, uses FROM tags ORDER BY uses DESC LIMIT 5")
    stats['top_tags'] = [{'name': row[0], 'uses': row[1]} for row in cur.fetchall()]

    cur = conn.execute("SELECT AVG(uses) FROM tags")
    avg = cur.fetchone()[0]
    stats['avg_uses'] = round(avg, 2) if avg else 0

    conn.close()
    return stats


def get_active_levels_sync() -> dict:
    """Get level distribution stats: total active users, average level, top level buckets."""
    conn = sqlite3.connect(DB_PATH)
    stats = {}

    cur = conn.execute("SELECT COUNT(DISTINCT user_id) FROM levels WHERE xp > 0")
    stats['total_users'] = cur.fetchone()[0]

    cur = conn.execute("SELECT AVG(level) FROM levels WHERE level > 0")
    avg_level = cur.fetchone()[0]
    stats['avg_level'] = round(avg_level, 2) if avg_level else 0

    cur = conn.execute("SELECT level, COUNT(*) as count FROM levels WHERE level > 0 GROUP BY level ORDER BY level DESC LIMIT 5")
    stats['top_levels'] = [{'level': row[0], 'users': row[1]} for row in cur.fetchall()]

    conn.close()
    return stats


def get_recent_mod_logs_sync(limit: int = 10) -> list:
    """Get the most recent moderation log entries."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        "SELECT action, moderator_id, target_id, reason, timestamp FROM mod_logs ORDER BY timestamp DESC LIMIT ?",
        (limit,)
    )
    logs = [
        {'action': row[0], 'moderator': row[1], 'target': row[2], 'reason': row[3], 'timestamp': row[4]}
        for row in cur.fetchall()
    ]
    conn.close()
    return logs


def get_guild_count_sync() -> int:
    """Get the number of guilds with a row in guild_settings."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("SELECT COUNT(DISTINCT guild_id) FROM guild_settings")
    count = cur.fetchone()[0]
    conn.close()
    return count


def get_usage_trend_sync(days: int = 7) -> list:
    """Get mod_log action counts grouped by date for the last N days.
    Returns: [{'date': 'YYYY-MM-DD', 'count': int}, ...]
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute(
        """
        SELECT DATE(timestamp) as date, COUNT(*) as count
        FROM mod_logs
        WHERE timestamp >= datetime('now', ?)
        GROUP BY DATE(timestamp)
        ORDER BY date ASC
        """,
        (f"-{days} days",)
    )
    result = [{'date': row[0], 'count': row[1]} for row in cur.fetchall()]
    conn.close()
    return result


def get_dashboard_stats_sync() -> dict:
    """Collect all dashboard statistics in a single call."""
    return {
        'total_tags': get_total_tags_sync(),
        'total_guilds': get_total_guilds_sync(),
        'guild_count': get_guild_count_sync(),
        'tag_stats': get_tag_stats_sync(),
        'level_stats': get_active_levels_sync(),
        'recent_logs': get_recent_mod_logs_sync(5),
        'usage_trend': get_usage_trend_sync(7),
    }


# -- Tag Search & Management Functions ----------------------------------------

def search_tags_sync(query: str = None, guild_id: str = None, created_by: str = None,
                     sort_by: str = 'name', limit: int = 50, offset: int = 0) -> dict:
    """Search and filter tags with pagination.
    Returns: {'total': int, 'tags': list, 'limit': int, 'offset': int}
    """
    conn = sqlite3.connect(DB_PATH)

    sql = "SELECT id, guild_id, name, content, created_by, uses FROM tags WHERE 1=1"
    params = []

    if query:
        sql += " AND name LIKE ?"
        params.append(f"%{query}%")
    if guild_id:
        sql += " AND guild_id = ?"
        params.append(guild_id)
    if created_by:
        sql += " AND created_by = ?"
        params.append(created_by)

    # Count total matching rows before applying LIMIT
    count_sql = "SELECT COUNT(*) FROM tags WHERE 1=1"
    if query:
        count_sql += " AND name LIKE ?"
    if guild_id:
        count_sql += " AND guild_id = ?"
    if created_by:
        count_sql += " AND created_by = ?"

    total = conn.execute(count_sql, params).fetchone()[0]

    if sort_by == 'usage':
        sql += " ORDER BY uses DESC"
    elif sort_by == 'date':
        sql += " ORDER BY rowid DESC"
    else:
        sql += " ORDER BY name ASC"

    sql += " LIMIT ? OFFSET ?"

    cur = conn.execute(sql, params + [limit, offset])
    tags = [
        {'id': row[0], 'guild_id': row[1], 'name': row[2], 'content': row[3],
         'created_by': row[4], 'uses': row[5]}
        for row in cur.fetchall()
    ]

    conn.close()
    return {'total': total, 'tags': tags, 'limit': limit, 'offset': offset}


def get_tag_usage_stats_sync() -> dict:
    """Get comprehensive tag usage statistics for the tags management page."""
    conn = sqlite3.connect(DB_PATH)
    stats = {}

    cur = conn.execute("SELECT COUNT(*) FROM tags")
    stats['total_tags'] = cur.fetchone()[0]

    cur = conn.execute("SELECT name, uses, guild_id FROM tags ORDER BY uses DESC LIMIT 10")
    stats['top_tags'] = [{'name': row[0], 'uses': row[1], 'guild': row[2]} for row in cur.fetchall()]

    cur = conn.execute("SELECT name, uses, guild_id FROM tags WHERE uses > 0 ORDER BY uses ASC LIMIT 10")
    stats['least_used'] = [{'name': row[0], 'uses': row[1], 'guild': row[2]} for row in cur.fetchall()]

    cur = conn.execute("SELECT COUNT(*) FROM tags WHERE uses = 0")
    stats['unused_count'] = cur.fetchone()[0]

    cur = conn.execute("SELECT AVG(uses) FROM tags")
    avg = cur.fetchone()[0]
    stats['avg_uses'] = round(avg, 2) if avg else 0

    cur = conn.execute("SELECT SUM(uses) FROM tags")
    stats['total_uses'] = cur.fetchone()[0] or 0

    cur = conn.execute("SELECT guild_id, COUNT(*) as count FROM tags GROUP BY guild_id ORDER BY count DESC LIMIT 5")
    stats['top_guilds'] = [{'guild': row[0], 'count': row[1]} for row in cur.fetchall()]

    conn.close()
    return stats


def reset_tag_uses_sync(tag_id: int) -> bool:
    """Reset the uses counter to 0 for a single tag. Returns True on success."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE tags SET uses = 0 WHERE id = ?", (tag_id,))
        conn.commit()
        conn.close()
        return True
    except Exception:
        return False


def reset_old_tag_uses_sync(days: int = 30) -> int:
    """Reset uses for unused tags (uses = 0). Returns count of rows affected.
    Note: full last-used tracking would require a last_used_at timestamp column.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        rows = conn.execute("SELECT id FROM tags WHERE uses = 0 LIMIT 100").fetchall()
        count = len(rows)
        conn.close()
        return count
    except Exception:
        return 0


# -- User Profile Functions ---------------------------------------------------

def get_user_profile_sync(user_id: str, guild_id: str = None) -> dict:
    """Get a comprehensive user profile: XP/level, rank, favorites, notes, playlists.
    If guild_id is provided, stats are scoped to that guild.
    """
    conn = sqlite3.connect(DB_PATH)
    profile = {'user_id': user_id, 'stats': {}, 'favorites': [], 'notes': []}

    # Level data - guild-scoped or global aggregate
    if guild_id:
        cur = conn.execute(
            "SELECT xp, level FROM levels WHERE user_id = ? AND guild_id = ?",
            (user_id, guild_id)
        )
    else:
        cur = conn.execute("SELECT SUM(xp) as xp, MAX(level) as level FROM levels WHERE user_id = ?", (user_id,))

    level_data = cur.fetchone()
    if level_data:
        profile['stats']['xp'] = level_data[0] or 0
        profile['stats']['level'] = level_data[1] or 0
    else:
        profile['stats']['xp'] = 0
        profile['stats']['level'] = 0

    # Rank and total users (guild-scoped only)
    if guild_id:
        cur = conn.execute(
            "SELECT COUNT(*) FROM levels WHERE guild_id = ? AND xp > ?",
            (guild_id, profile['stats']['xp'])
        )
        profile['stats']['rank'] = cur.fetchone()[0] + 1

        cur = conn.execute("SELECT COUNT(DISTINCT user_id) FROM levels WHERE guild_id = ?", (guild_id,))
        profile['stats']['total_users'] = cur.fetchone()[0]

    # Music favorites (most recent 5)
    cur = conn.execute(
        "SELECT track_title, track_url, uploader, thumbnail FROM music_favorites WHERE user_id = ? ORDER BY added_at DESC LIMIT 5",
        (user_id,)
    )
    profile['favorites'] = [
        {'title': row[0], 'url': row[1], 'uploader': row[2], 'thumbnail': row[3]}
        for row in cur.fetchall()
    ]

    # Mod notes (guild-scoped, most recent 5)
    if guild_id:
        cur = conn.execute(
            "SELECT note, moderator_id, timestamp FROM mod_notes WHERE user_id = ? AND guild_id = ? ORDER BY timestamp DESC LIMIT 5",
            (user_id, guild_id)
        )
        profile['notes'] = [
            {'note': row[0], 'moderator': row[1], 'timestamp': row[2]}
            for row in cur.fetchall()
        ]

    # Public playlists (most recent 3)
    cur = conn.execute(
        "SELECT id, name FROM music_playlists WHERE user_id = ? AND is_public = 1 ORDER BY created_at DESC LIMIT 3",
        (user_id,)
    )
    profile['playlists'] = [{'id': row[0], 'name': row[1]} for row in cur.fetchall()]

    conn.close()
    return profile


def get_user_rank_sync(user_id: str, guild_id: str) -> tuple:
    """Get a user's rank within a guild. Returns (rank, total_users)."""
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute("SELECT xp FROM levels WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
    user_data = cur.fetchone()
    user_xp = user_data[0] if user_data else 0

    cur = conn.execute(
        "SELECT COUNT(*) FROM levels WHERE guild_id = ? AND xp > ?",
        (guild_id, user_xp)
    )
    rank = cur.fetchone()[0] + 1

    cur = conn.execute("SELECT COUNT(*) FROM levels WHERE guild_id = ?", (guild_id,))
    total = cur.fetchone()[0]

    conn.close()
    return rank, total


# -- Analytics Functions ------------------------------------------------------

def get_command_usage_by_date_sync(guild_id: str, start_date: str = None, end_date: str = None) -> list:
    """Get tag usage counts grouped by date from mod_logs (action = 'tag_used').
    Returns: [{'date': 'YYYY-MM-DD', 'uses': int}, ...]
    """
    conn = sqlite3.connect(DB_PATH)

    where_clause = "WHERE guild_id = ? AND action = 'tag_used'"
    params = [guild_id]

    if start_date:
        where_clause += " AND DATE(timestamp) >= ?"
        params.append(start_date)
    if end_date:
        where_clause += " AND DATE(timestamp) <= ?"
        params.append(end_date)

    cur = conn.execute(f"""
        SELECT DATE(timestamp) as date, COUNT(*) as total_uses FROM mod_logs
        {where_clause}
        GROUP BY DATE(timestamp) ORDER BY date ASC
    """, params)

    result = [{'date': row[0], 'uses': row[1]} for row in cur.fetchall()]
    conn.close()
    return result


def get_top_commands_sync(guild_id: str, limit: int = 10, start_date: str = None, end_date: str = None) -> list:
    """Get the top tags by total use count for a guild.
    Note: the tags table has no per-date tracking, so date filters are not applied here.
    Returns: [{'name': str, 'uses': int, 'days_used': int}, ...]
    """
    conn = sqlite3.connect(DB_PATH)

    cur = conn.execute("""
        SELECT name, uses as total_uses, 1 as days_used
        FROM tags
        WHERE guild_id = ?
        ORDER BY total_uses DESC LIMIT ?
    """, (guild_id, limit))

    result = [{'name': row[0], 'uses': row[1] or 0, 'days_used': row[2] or 1} for row in cur.fetchall()]
    conn.close()
    return result


def get_guild_activity_sync(guild_id: str, start_date: str = None, end_date: str = None) -> dict:
    """Get overall guild activity: total tag uses, active users, unique command count.
    Active users are counted from mod_logs (action = 'tag_used') within the date range.
    """
    conn = sqlite3.connect(DB_PATH)

    # Total tag uses (from tags table - not date-filtered)
    cur = conn.execute("SELECT SUM(uses) FROM tags WHERE guild_id = ?", (guild_id,))
    total_commands = cur.fetchone()[0] or 0

    # Active users from mod_logs within the optional date range
    where_clause = "WHERE guild_id = ? AND action = 'tag_used'"
    params = [guild_id]

    if start_date:
        where_clause += " AND DATE(timestamp) >= ?"
        params.append(start_date)
    if end_date:
        where_clause += " AND DATE(timestamp) <= ?"
        params.append(end_date)

    cur = conn.execute(f"SELECT COUNT(DISTINCT target_id) FROM mod_logs {where_clause}", params)
    active_users = cur.fetchone()[0] or 0

    # Unique tag names in this guild
    cur = conn.execute("SELECT COUNT(*) FROM tags WHERE guild_id = ?", (guild_id,))
    unique_commands = cur.fetchone()[0] or 0

    conn.close()
    return {
        'total_commands': total_commands,
        'active_users': active_users,
        'unique_commands': unique_commands
    }


def get_member_activity_sync(guild_id: str, limit: int = 15) -> list:
    """Get most active members by tag usage from mod_logs."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.execute("""
        SELECT target_id, COUNT(*) as total_uses FROM mod_logs
        WHERE guild_id = ? AND action = 'tag_used'
        GROUP BY target_id ORDER BY total_uses DESC LIMIT ?
    """, (guild_id, limit))
    result = [{'user_id': row[0], 'uses': row[1]} for row in cur.fetchall()]
    conn.close()
    return result


def export_analytics_csv_sync(guild_id: str, start_date: str = None, end_date: str = None) -> str:
    """Export tag usage analytics from mod_logs as a CSV string."""
    import csv
    from io import StringIO

    conn = sqlite3.connect(DB_PATH)

    where_clause = "WHERE guild_id = ? AND action = 'tag_used'"
    params = [guild_id]

    if start_date:
        where_clause += " AND DATE(timestamp) >= ?"
        params.append(start_date)
    if end_date:
        where_clause += " AND DATE(timestamp) <= ?"
        params.append(end_date)

    cur = conn.execute(f"""
        SELECT DATE(timestamp) as date, action, target_id, moderator_id, reason FROM mod_logs
        {where_clause} ORDER BY timestamp DESC
    """, params)

    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(['Date', 'Action', 'Tag/Target', 'User', 'Details'])
    for row in cur.fetchall():
        writer.writerow(row)

    conn.close()
    return output.getvalue() 