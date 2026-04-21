import os, sys, sqlite3, math, requests
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

OAUTH_URL = (
    'https://discord.com/api/oauth2/authorize'
    f'?client_id={CLIENT_ID}'
    f'&redirect_uri={requests.utils.quote(REDIRECT_URI, safe="")}'
    '&response_type=code&scope=identify+guilds'
)

# ── Helpers ───────────────────────────────────────────────────────────────────

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

def get_pterodactyl_servers():
    if not PTERODACTYL_API_KEY:
        return None, "PTERODACTYL_API_KEY not set in .env"
    base  = PTERODACTYL_URL.rstrip("/")
    hdrs  = {"Authorization": f"Bearer {PTERODACTYL_API_KEY}", "Accept": "application/json"}
    try:
        data = requests.get(f"{base}/api/client/servers", headers=hdrs, timeout=8).json()
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

# ── Auth ─────────────────────────────────────────────────────────────────────

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

# ── Dashboard ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    conn = get_db()
    warn_count   = conn.execute('SELECT COUNT(*) FROM warnings').fetchone()[0]
    tag_count    = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
    log_count    = conn.execute('SELECT COUNT(*) FROM mod_logs').fetchone()[0]
    ranked_count = conn.execute('SELECT COUNT(*) FROM levels').fetchone()[0]
    note_count   = conn.execute('SELECT COUNT(*) FROM mod_notes').fetchone()[0]
    recent_logs  = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 5').fetchall()
    top_users    = conn.execute('SELECT user_id, xp, level FROM levels ORDER BY xp DESC LIMIT 5').fetchall()
    conn.close()
    ptero_servers, ptero_error = get_pterodactyl_servers()
    return render_template('index.html',
        user=session['user'],
        warn_count=warn_count, tag_count=tag_count,
        log_count=log_count, ranked_count=ranked_count, note_count=note_count,
        recent_logs=recent_logs, top_users=top_users,
        ptero_servers=ptero_servers, ptero_error=ptero_error)

# ── Pterodactyl ─────────────────────────────────────────────────────────────

@app.route('/pterodactyl')
@login_required
def pterodactyl():
    servers, error = get_pterodactyl_servers()
    return render_template('pterodactyl.html', user=session['user'], servers=servers, error=error)

# ── Mod Logs ─────────────────────────────────────────────────────────────────

@app.route('/modlogs')
@login_required
def modlogs():
    conn = get_db()
    logs = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 200').fetchall()
    conn.close()
    return render_template('modlogs.html', user=session['user'], logs=logs)

# ── Mod Notes ─────────────────────────────────────────────────────────────────

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

# ── Leaderboard ─────────────────────────────────────────────────────────────

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

# ── Tags ───────────────────────────────────────────────────────────────────────

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

# ── AutoMod ───────────────────────────────────────────────────────────────────

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

# ── Settings ─────────────────────────────────────────────────────────────────

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

if __name__ == '__main__':
    db_module.init_db_sync()
    app.run(host='0.0.0.0', port=5000, debug=False)
