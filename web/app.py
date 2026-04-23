import os, sys, sqlite3, math, requests, json
from flask import Flask, render_template, redirect, request, session, url_for, flash
from functools import wraps
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database as db_module

load_dotenv(os.path.join(ROOT, '.env'))

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me')
app.jinja_env.variable_start_string = '<%'
app.jinja_env.variable_end_string   = '%>'

DB_PATH             = os.getenv('DB_PATH', '/data/omni.db')
CLIENT_ID           = os.getenv('DISCORD_CLIENT_ID', '1494509191749042237')
CLIENT_SECRET       = os.getenv('DISCORD_CLIENT_SECRET', '')
REDIRECT_URI        = os.getenv('DISCORD_REDIRECT_URI', 'https://omni-endpoint.crystal-kitsune-studios.com/callback')
GUILD_ID            = os.getenv('GUILD_ID', '')
PTERODACTYL_URL     = os.getenv('PTERODACTYL_URL', 'https://panel.starlightsserverhosting.uk')
PTERODACTYL_API_KEY = os.getenv('PTERODACTYL_API_KEY', '')
GROQ_API_KEY        = os.getenv('GROQ_API_KEY', '')

OAUTH_URL = (
    'https://discord.com/api/oauth2/authorize'
    f'?client_id={CLIENT_ID}'
    f'&redirect_uri={requests.utils.quote(REDIRECT_URI, safe="")}'
    '&response_type=code&scope=identify+guilds'
)

GROQ_MODEL   = 'llama-3.3-70b-versatile'
GROQ_HEADERS = lambda: {'Authorization': f'Bearer {GROQ_API_KEY}', 'Content-Type': 'application/json'}

# ── Helpers ───────────────────────────────────────────────────────────────

def level_from_xp(xp):
    if not xp or xp <= 0: return 0
    return int((-1 + math.sqrt(1 + 4 * xp / 50)) / 2)

def xp_for_level(level):
    return 100 * level * (level + 1) // 2

def xp_progress(xp):
    level = level_from_xp(xp)
    floor = xp_for_level(level)
    nxt   = xp_for_level(level + 1)
    xp_in = xp - floor
    need  = nxt - floor
    return level, xp_in, need, round((xp_in / need) * 100) if need else 100

app.jinja_env.globals['level_from_xp'] = level_from_xp
app.jinja_env.globals['xp_progress']   = xp_progress

def _uptime_str(ms):
    s = ms // 1000
    d, r = divmod(s, 86400); h, r = divmod(r, 3600); m = r // 60
    parts = []
    if d: parts.append(f"{d}d")
    if h: parts.append(f"{h}h")
    parts.append(f"{m}m")
    return " ".join(parts) if parts else "0m"

# ── Pterodactyl ───────────────────────────────────────────────────────────

def get_pterodactyl_servers():
    if not PTERODACTYL_API_KEY:
        return None, "PTERODACTYL_API_KEY not set in .env"
    base  = PTERODACTYL_URL.rstrip("/")
    hdrs  = {"Authorization": f"Bearer {PTERODACTYL_API_KEY}", "Accept": "application/json"}
    try:
        data = requests.get(f"{base}/api/client", headers=hdrs, timeout=8).json()
        servers = []
        for s in data.get("data", []):
            attr   = s.get("attributes", {})
            sid    = attr.get("identifier", "")
            limits = attr.get("limits", {})
            try:
                res      = requests.get(f"{base}/api/client/servers/{sid}/resources", headers=hdrs, timeout=5).json()
                ra       = res.get("attributes", {})
                state    = ra.get("current_state", "unknown")
                rr       = ra.get("resources", {})
                mem_mb   = round(rr.get("memory_bytes", 0) / 1024**2, 1)
                disk_mb  = round(rr.get("disk_bytes",   0) / 1024**2, 1)
                mem_lim  = limits.get("memory", 0)
                disk_lim = limits.get("disk",   0)
                servers.append({
                    "name":          attr.get("name", "Unknown"),
                    "identifier":    sid,
                    "state":         state,
                    "cpu":           round(rr.get("cpu_absolute", 0), 1),
                    "cpu_limit":     limits.get("cpu", 100),
                    "mem_mb":        mem_mb,
                    "mem_limit_mb":  mem_lim,
                    "mem_pct":       round((mem_mb  / mem_lim)  * 100) if mem_lim  else 0,
                    "disk_mb":       disk_mb,
                    "disk_limit_mb": disk_lim,
                    "disk_pct":      round((disk_mb / disk_lim) * 100) if disk_lim else 0,
                    "uptime":        _uptime_str(rr.get("uptime", 0)) if state == "running" else "\u2014",
                })
            except Exception as e:
                servers.append({"name": attr.get("name", "?"), "identifier": sid, "state": "unknown", "error": str(e)})
        return servers, None
    except Exception as e:
        return None, str(e)

# ── Docker ──────────────────────────────────────────────────────────────

def get_docker_stats():
    try:
        import docker as docker_sdk
        client = docker_sdk.DockerClient(base_url='unix://var/run/docker.sock')
        containers = client.containers.list(all=True)
        result = []
        for c in containers:
            status = c.status
            cpu_pct = mem_mb = mem_limit_mb = mem_pct = 0
            if status == 'running':
                try:
                    s         = c.stats(stream=False)
                    cpu_delta = s['cpu_stats']['cpu_usage']['total_usage'] - s['precpu_stats']['cpu_usage']['total_usage']
                    sys_delta = s['cpu_stats']['system_cpu_usage'] - s['precpu_stats']['system_cpu_usage']
                    num_cpus  = s['cpu_stats'].get('online_cpus') or len(s['cpu_stats']['cpu_usage'].get('percpu_usage', [None]))
                    cpu_pct   = round((cpu_delta / sys_delta) * num_cpus * 100.0, 1) if sys_delta > 0 else 0.0
                    mem_usage = s['memory_stats']['usage'] - s['memory_stats'].get('stats', {}).get('cache', 0)
                    mem_limit = s['memory_stats']['limit']
                    mem_mb    = round(mem_usage / 1024**2, 1)
                    mem_limit_mb = round(mem_limit / 1024**2, 1)
                    mem_pct   = round((mem_mb / mem_limit_mb) * 100) if mem_limit_mb else 0
                except Exception:
                    pass
            result.append({
                'name':         c.name,
                'short_id':     c.short_id,
                'image':        c.image.tags[0] if c.image.tags else c.image.short_id,
                'status':       status,
                'cpu_pct':      cpu_pct,
                'mem_mb':       mem_mb,
                'mem_limit_mb': mem_limit_mb,
                'mem_pct':      mem_pct,
            })
        client.close()
        result.sort(key=lambda x: x['status'] != 'running')
        return result, None
    except Exception as e:
        return None, str(e)

def get_db():
    db_module.init_db_sync()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Auth ──────────────────────────────────────────────────────────────────

@app.route('/login')
def login():
    return render_template('login.html', oauth_url=OAUTH_URL)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    if not code:
        flash('OAuth2 failed.', 'danger')
        return redirect(url_for('login'))
    r = requests.post('https://discord.com/api/oauth2/token', data={
        'client_id': CLIENT_ID, 'client_secret': CLIENT_SECRET,
        'grant_type': 'authorization_code', 'code': code, 'redirect_uri': REDIRECT_URI,
    })
    if not r.ok:
        flash('Token exchange failed.', 'danger')
        return redirect(url_for('login'))
    token = r.json().get('access_token')
    user  = requests.get('https://discord.com/api/users/@me',
                         headers={'Authorization': f'Bearer {token}'}).json()
    if 'id' not in user:
        flash('Could not fetch user info.', 'danger')
        return redirect(url_for('login'))
    session['user']  = user
    session['token'] = token
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Dashboard ───────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    conn = get_db()
    warn_count    = conn.execute('SELECT COUNT(*) FROM warnings').fetchone()[0]
    tag_count     = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
    log_count     = conn.execute('SELECT COUNT(*) FROM mod_logs').fetchone()[0]
    ranked_count  = conn.execute('SELECT COUNT(*) FROM levels').fetchone()[0]
    note_count    = conn.execute('SELECT COUNT(*) FROM mod_notes').fetchone()[0]
    appeal_count  = conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status = 'open'").fetchone()[0]
    recent_logs   = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 5').fetchall()
    top_users     = conn.execute('SELECT user_id, xp, level FROM levels ORDER BY xp DESC LIMIT 5').fetchall()
    conn.close()
    ptero_servers, ptero_error      = get_pterodactyl_servers()
    docker_containers, docker_error = get_docker_stats()
    return render_template('index.html',
        user=session['user'],
        warn_count=warn_count, tag_count=tag_count,
        log_count=log_count, ranked_count=ranked_count, note_count=note_count,
        appeal_count=appeal_count,
        recent_logs=recent_logs, top_users=top_users,
        ptero_servers=ptero_servers, ptero_error=ptero_error,
        docker_containers=docker_containers, docker_error=docker_error)

@app.route('/dashboard')
@login_required
def dashboard():
    """Enhanced dashboard with comprehensive bot statistics."""
    try:
        stats = db_module.get_dashboard_stats_sync()
        conn = get_db()
        appeal_count = conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status = 'pending'").fetchone()[0]
        conn.close()
        stats['pending_appeals'] = appeal_count
        return render_template('dashboard.html', user=session['user'], stats=stats)
    except Exception as e:
        print(f"[Dashboard Error] {e}")
        flash(f'Dashboard error: {e}', 'danger')
        return redirect(url_for('index'))

# ── Groq AI ──────────────────────────────────────────────────────────────

@app.route('/ai', methods=['GET', 'POST'])
@login_required
def ai_chat():
    if 'ai_history' not in session:
        session['ai_history'] = []
    error = None
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'clear':
            session['ai_history'] = []
            session.modified = True
            return redirect(url_for('ai_chat'))
        user_msg = request.form.get('message', '').strip()
        if user_msg and GROQ_API_KEY:
            history = list(session['ai_history'])
            history.append({'role': 'user', 'content': user_msg})
            payload = {
                'model': GROQ_MODEL,
                'messages': [
                    {'role': 'system', 'content': 'You are OMNI, a helpful AI assistant for Crystal Kitsune Studios. Be concise and direct.'}
                ] + history,
                'max_tokens': 1024,
                'temperature': 0.7,
            }
            try:
                r = requests.post(
                    'https://api.groq.com/openai/v1/chat/completions',
                    headers=GROQ_HEADERS(),
                    json=payload,
                    timeout=30
                )
                r.raise_for_status()
                reply = r.json()['choices'][0]['message']['content']
                history.append({'role': 'assistant', 'content': reply})
                session['ai_history'] = history[-40:]  # keep last 20 exchanges
                session.modified = True
            except requests.HTTPError as e:
                error = f'Groq API error: {e.response.status_code} — {e.response.text[:200]}'
            except Exception as e:
                error = str(e)
        elif not GROQ_API_KEY:
            error = 'GROQ_API_KEY not set in .env'
    return render_template('ai.html', user=session['user'],
                           history=session.get('ai_history', []),
                           model=GROQ_MODEL, error=error,
                           groq_configured=bool(GROQ_API_KEY))

# ── Ban Appeals (public) ──────────────────────────────────────────────

@app.route('/appeal', methods=['GET', 'POST'])
def appeal():
    if request.method == 'POST':
        username   = request.form.get('discord_username', '').strip()
        discord_id = request.form.get('discord_id', '').strip()
        ban_reason = request.form.get('ban_reason', '').strip()
        appeal_msg = request.form.get('appeal_message', '').strip()
        if not username or not discord_id or not appeal_msg:
            flash('Please fill in all required fields.', 'danger')
            return render_template('appeal.html')
        if not discord_id.isdigit():
            flash('Discord ID must be a number (e.g. 123456789012345678).', 'danger')
            return render_template('appeal.html')
        conn = get_db()
        existing = conn.execute(
            "SELECT id FROM ban_appeals WHERE discord_id = ? AND status IN ('pending','open')",
            (discord_id,)
        ).fetchone()
        if existing:
            conn.close()
            flash('You already have an open appeal being reviewed.', 'warning')
            return render_template('appeal.html')
        conn.execute(
            'INSERT INTO ban_appeals (discord_username, discord_id, ban_reason, appeal_message) VALUES (?,?,?,?)',
            (username, discord_id, ban_reason, appeal_msg)
        )
        conn.commit()
        conn.close()
        flash('Your appeal has been submitted! Staff will review it shortly.', 'success')
        return render_template('appeal.html', submitted=True)
    return render_template('appeal.html')

# ── Ban Appeals (staff) ───────────────────────────────────────────────

@app.route('/appeals')
@login_required
def appeals():
    status_filter = request.args.get('status', 'all')
    conn = get_db()
    if status_filter != 'all':
        rows = conn.execute('SELECT * FROM ban_appeals WHERE status = ? ORDER BY created_at DESC', (status_filter,)).fetchall()
    else:
        rows = conn.execute('SELECT * FROM ban_appeals ORDER BY created_at DESC').fetchall()
    counts = {
        'pending': conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status='pending'").fetchone()[0],
        'open':    conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status='open'").fetchone()[0],
        'accept':  conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status='accept'").fetchone()[0],
        'deny':    conn.execute("SELECT COUNT(*) FROM ban_appeals WHERE status='deny'").fetchone()[0],
    }
    conn.close()
    return render_template('appeals.html', user=session['user'], appeals=rows,
                           status_filter=status_filter, counts=counts)

# ── Pterodactyl ───────────────────────────────────────────────────────────

@app.route('/pterodactyl')
@login_required
def pterodactyl():
    servers, error = get_pterodactyl_servers()
    return render_template('pterodactyl.html', user=session['user'], servers=servers, error=error)

# ── Docker ──────────────────────────────────────────────────────────────

@app.route('/docker')
@login_required
def docker_page():
    containers, error = get_docker_stats()
    return render_template('docker.html', user=session['user'], containers=containers, error=error)

# ── Mod Logs ────────────────────────────────────────────────────────────

@app.route('/modlogs')
@login_required
def modlogs():
    conn = get_db()
    logs = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 200').fetchall()
    conn.close()
    return render_template('modlogs.html', user=session['user'], logs=logs)

# ── Mod Notes ────────────────────────────────────────────────────────────

@app.route('/modnotes')
@login_required
def modnotes():
    search = request.args.get('q', '').strip()
    conn   = get_db()
    if search:
        notes = conn.execute(
            'SELECT * FROM mod_notes WHERE user_id LIKE ? ORDER BY timestamp DESC LIMIT 200',
            (f'%{search}%',)
        ).fetchall()
    else:
        notes = conn.execute('SELECT * FROM mod_notes ORDER BY timestamp DESC LIMIT 200').fetchall()
    conn.close()
    return render_template('modnotes.html', user=session['user'], notes=notes, search=search)

@app.route('/modnotes/delete/<int:note_id>', methods=['POST'])
@login_required
def delete_note(note_id):
    conn = get_db()
    conn.execute('DELETE FROM mod_notes WHERE id=?', (note_id,))
    conn.commit()
    conn.close()
    flash('Note deleted.', 'success')
    return redirect(url_for('modnotes'))

# ── Leaderboard ──────────────────────────────────────────────────────────

@app.route('/leaderboard')
@login_required
def leaderboard():
    conn  = get_db()
    rows  = conn.execute('SELECT user_id, xp, level FROM levels ORDER BY xp DESC LIMIT 100').fetchall()
    total = conn.execute('SELECT COUNT(*) FROM levels').fetchone()[0]
    conn.close()
    return render_template('leaderboard.html', user=session['user'], rows=rows, total=total)

@app.route('/leaderboard/reset/<user_id>', methods=['POST'])
@login_required
def reset_user_xp(user_id):
    conn = get_db()
    conn.execute('DELETE FROM levels WHERE user_id=?', (user_id,))
    conn.commit()
    conn.close()
    flash(f'XP reset for user {user_id}.', 'success')
    return redirect(url_for('leaderboard'))

# ── Tags ──────────────────────────────────────────────────────────────────

@app.route('/commands')
@login_required
def commands():
    conn = get_db()
    tags = conn.execute('SELECT * FROM tags ORDER BY name').fetchall()
    conn.close()
    return render_template('commands.html', user=session['user'], tags=tags)

@app.route('/commands/add', methods=['POST'])
@login_required
def add_command():
    name    = request.form.get('name', '').lower().strip()
    content = request.form.get('content', '').strip()
    if not name or not content:
        flash('Name and content required.', 'danger')
        return redirect(url_for('commands'))
    conn = get_db()
    try:
        conn.execute('INSERT INTO tags (guild_id,name,content,created_by) VALUES (?,?,?,?)',
                     (GUILD_ID, name, content, session['user']['id']))
        conn.commit()
        flash(f'Tag "{name}" created.', 'success')
    except sqlite3.IntegrityError:
        flash(f'Tag "{name}" already exists.', 'danger')
    finally:
        conn.close()
    return redirect(url_for('commands'))

@app.route('/commands/edit/<int:tag_id>', methods=['POST'])
@login_required
def edit_command(tag_id):
    content = request.form.get('content', '').strip()
    if not content:
        flash('Content cannot be empty.', 'danger')
        return redirect(url_for('commands'))
    conn = get_db()
    conn.execute('UPDATE tags SET content=? WHERE id=?', (content, tag_id))
    conn.commit()
    conn.close()
    flash('Tag updated.', 'success')
    return redirect(url_for('commands'))

@app.route('/commands/delete/<int:tag_id>', methods=['POST'])
@login_required
def delete_command(tag_id):
    conn = get_db()
    conn.execute('DELETE FROM tags WHERE id=?', (tag_id,))
    conn.commit()
    conn.close()
    flash('Tag deleted.', 'success')
    return redirect(url_for('commands'))

@app.route('/commands/search')
@login_required
def search_commands():
    """API endpoint for searching and filtering tags."""
    query = request.args.get('q', '').strip()
    guild_id = request.args.get('guild', '').strip()
    created_by = request.args.get('creator', '').strip()
    sort_by = request.args.get('sort', 'name')
    limit = min(int(request.args.get('limit', 50)), 100)
    offset = int(request.args.get('offset', 0))
    
    result = db_module.search_tags_sync(query, guild_id, created_by, sort_by, limit, offset)
    return json.dumps(result)

@app.route('/commands/stats')
@login_required
def tag_stats():
    """API endpoint for tag usage statistics."""
    stats = db_module.get_tag_usage_stats_sync()
    return json.dumps(stats)

@app.route('/commands/bulk-delete', methods=['POST'])
@login_required
def bulk_delete_tags():
    """Bulk delete tags by ID list."""
    tag_ids = request.form.getlist('tag_ids[]')
    if not tag_ids:
        flash('No tags selected.', 'warning')
        return redirect(url_for('commands'))
    
    try:
        conn = get_db()
        for tag_id in tag_ids:
            conn.execute('DELETE FROM tags WHERE id=?', (tag_id,))
        conn.commit()
        conn.close()
        flash(f'Deleted {len(tag_ids)} tag(s).', 'success')
    except Exception as e:
        flash(f'Error deleting tags: {e}', 'danger')
    
    return redirect(url_for('commands'))

@app.route('/commands/reset-uses', methods=['POST'])
@login_required
def reset_tag_uses():
    """Reset uses count for selected tags."""
    tag_ids = request.form.getlist('tag_ids[]')
    if not tag_ids:
        flash('No tags selected.', 'warning')
        return redirect(url_for('commands'))
    
    try:
        for tag_id in tag_ids:
            db_module.reset_tag_uses_sync(tag_id)
        flash(f'Reset uses for {len(tag_ids)} tag(s).', 'success')
    except Exception as e:
        flash(f'Error resetting uses: {e}', 'danger')
    
    return redirect(url_for('commands'))

# ── AutoMod ─────────────────────────────────────────────────────────────

@app.route('/automod')
@login_required
def automod():
    conn = get_db()
    s = conn.execute('SELECT * FROM guild_settings WHERE guild_id=?', (GUILD_ID,)).fetchone()
    conn.close()
    return render_template('automod.html', user=session['user'], settings=s)

@app.route('/automod/save', methods=['POST'])
@login_required
def save_automod():
    spam   = 1 if request.form.get('automod_spam') else 0
    caps   = 1 if request.form.get('automod_caps') else 0
    inv    = 1 if request.form.get('automod_invites') else 0
    thresh = int(request.form.get('automod_spam_threshold', 5))
    ratio  = float(request.form.get('automod_caps_ratio', 0.7))
    conn = get_db()
    conn.execute("""
        INSERT INTO guild_settings(guild_id,automod_spam,automod_caps,automod_invites,
            automod_spam_threshold,automod_caps_ratio) VALUES(?,?,?,?,?,?)
        ON CONFLICT(guild_id) DO UPDATE SET
            automod_spam=excluded.automod_spam, automod_caps=excluded.automod_caps,
            automod_invites=excluded.automod_invites,
            automod_spam_threshold=excluded.automod_spam_threshold,
            automod_caps_ratio=excluded.automod_caps_ratio
    """, (GUILD_ID, spam, caps, inv, thresh, ratio))
    conn.commit()
    conn.close()
    flash('AutoMod settings saved.', 'success')
    return redirect(url_for('automod'))

# ── Settings ─────────────────────────────────────────────────────────────

@app.route('/settings')
@login_required
def settings():
    conn = get_db()
    s = conn.execute('SELECT * FROM guild_settings WHERE guild_id=?', (GUILD_ID,)).fetchone()
    conn.close()
    return render_template('settings.html', user=session['user'], settings=s)

@app.route('/settings/save', methods=['POST'])
@login_required
def save_settings():
    f = request.form
    conn = get_db()
    conn.execute("""
        INSERT INTO guild_settings(guild_id,log_channel_id,welcome_channel_id,
            welcome_message,auto_role_id,starboard_channel_id,starboard_threshold)
        VALUES(?,?,?,?,?,?,?)
        ON CONFLICT(guild_id) DO UPDATE SET
            log_channel_id=excluded.log_channel_id,
            welcome_channel_id=excluded.welcome_channel_id,
            welcome_message=excluded.welcome_message,
            auto_role_id=excluded.auto_role_id,
            starboard_channel_id=excluded.starboard_channel_id,
            starboard_threshold=excluded.starboard_threshold
    """, (GUILD_ID,
          f.get('log_channel_id','').strip() or None,
          f.get('welcome_channel_id','').strip() or None,
          f.get('welcome_message','').strip() or 'Welcome {user} to {server}!',
          f.get('auto_role_id','').strip() or None,
          f.get('starboard_channel_id','').strip() or None,
          int(f.get('starboard_threshold', 3))))
    conn.commit()
    conn.close()
    flash('Settings saved.', 'success')
    return redirect(url_for('settings'))

# ── Music Routes ────────────────────────────────────────────────────────────

@app.route('/music')
@login_required
def music():
    return render_template('music.html', user=session['user'])

@app.route('/api/music/status')
@login_required
def api_music_status():
    """Get current now playing track, queue, volume, and loop state."""
    try:
        conn = get_db()
        current = conn.execute(
            'SELECT * FROM music_queue WHERE guild_id=? ORDER BY position ASC LIMIT 1',
            (GUILD_ID,)
        ).fetchone()
        queue_items = conn.execute(
            'SELECT * FROM music_queue WHERE guild_id=? ORDER BY position ASC LIMIT 50',
            (GUILD_ID,)
        ).fetchall()
        conn.close()
        
        result = {
            'current': None,
            'queue_length': len(queue_items) if queue_items else 0,
            'volume': 100,
            'loop': 'off'
        }
        
        if current:
            result['current'] = {
                'title': current[2],
                'url': current[3],
                'duration': current[5],
                'uploader': 'Unknown',
                'thumbnail': None
            }
        
        return result
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/play', methods=['POST'])
@login_required
def api_music_play():
    """Add a track to the queue by URL or search query."""
    try:
        data = request.get_json()
        query = data.get('query', '').strip()
        if not query:
            return {'error': 'Query required'}, 400
        
        # Here we'd call yt-dlp to extract metadata
        # For now, just store the query as URL
        conn = get_db()
        conn.execute(
            'INSERT INTO music_queue(guild_id, user_id, track_url, track_title, position, duration, added_at) VALUES(?,?,?,?,?,?,datetime("now"))',
            (GUILD_ID, session.get('user_id', 'web'), query, query, 0, 0)
        )
        conn.commit()
        conn.close()
        
        return {'success': True, 'message': 'Track added to queue'}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/control', methods=['POST'])
@login_required
def api_music_control():
    """Control playback: skip, pause, resume, stop, clear."""
    try:
        action = request.args.get('action', 'skip').lower()
        conn = get_db()
        
        if action == 'skip':
            conn.execute('DELETE FROM music_queue WHERE guild_id=? ORDER BY position ASC LIMIT 1', (GUILD_ID,))
        elif action == 'clear':
            conn.execute('DELETE FROM music_queue WHERE guild_id=?', (GUILD_ID,))
        elif action in ['pause', 'resume', 'stop']:
            pass  # Would interact with bot via IPC
        
        conn.commit()
        conn.close()
        return {'success': True}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/queue')
@login_required
def api_music_queue():
    """Get paginated queue."""
    try:
        page = int(request.args.get('page', 1))
        per_page = int(request.args.get('per_page', 10))
        offset = (page - 1) * per_page
        
        conn = get_db()
        queue_items = conn.execute(
            'SELECT * FROM music_queue WHERE guild_id=? ORDER BY position ASC LIMIT ? OFFSET ?',
            (GUILD_ID, per_page, offset)
        ).fetchall()
        total = conn.execute(
            'SELECT COUNT(*) FROM music_queue WHERE guild_id=?', (GUILD_ID,)
        ).fetchone()[0]
        conn.close()
        
        return {
            'queue': [
                {'position': q[4], 'title': q[2], 'url': q[3], 'duration': q[5]}
                for q in queue_items
            ],
            'total': total,
            'page': page,
            'per_page': per_page
        }
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/search')
@login_required
def api_music_search():
    """Search YouTube for tracks."""
    try:
        query = request.args.get('q', '').strip()
        if not query:
            return {'error': 'Query required'}, 400
        
        # Would call yt-dlp here
        # For now, return empty results
        return []
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/favorites', methods=['GET', 'POST'])
@login_required
def api_music_favorites():
    """Get or manage favorites."""
    try:
        conn = get_db()
        
        if request.method == 'GET':
            favorites = conn.execute(
                'SELECT * FROM music_favorites WHERE user_id=? ORDER BY added_at DESC',
                (session.get('user_id', 'web'),)
            ).fetchall()
            conn.close()
            return [
                {'track_url': f[1], 'track_title': f[2]}
                for f in favorites
            ]
        
        elif request.method == 'POST':
            data = request.get_json()
            action = data.get('action')
            
            if action == 'add':
                conn.execute(
                    'INSERT INTO music_favorites(user_id, track_url, track_title, added_at) VALUES(?,?,?,datetime("now"))',
                    (session.get('user_id', 'web'), data.get('url'), data.get('title'))
                )
            elif action == 'remove':
                conn.execute(
                    'DELETE FROM music_favorites WHERE user_id=? AND track_url=?',
                    (session.get('user_id', 'web'), data.get('url'))
                )
            
            conn.commit()
            conn.close()
            return {'success': True}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/volume', methods=['POST'])
@login_required
def api_music_volume():
    """Set volume level."""
    try:
        vol = int(request.args.get('vol', 100))
        vol = max(1, min(100, vol))
        return {'success': True, 'volume': vol}
    except Exception as e:
        return {'error': str(e)}, 500

@app.route('/api/music/loop', methods=['POST'])
@login_required
def api_music_loop():
    """Toggle loop mode."""
    try:
        return {'success': True, 'loop': 'on'}
    except Exception as e:
        return {'error': str(e)}, 500

if __name__ == '__main__':
    db_module.init_db_sync()
    app.run(host='0.0.0.0', port=5000, debug=False)
