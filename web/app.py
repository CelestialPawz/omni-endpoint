import os, sys, sqlite3, requests
from flask import Flask, render_template, redirect, request, session, url_for, flash
from functools import wraps
from dotenv import load_dotenv

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
import database as db_module

load_dotenv(os.path.join(ROOT, '.env'))

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'change-me')

DB_PATH       = os.getenv('DB_PATH', '/data/omni.db')
CLIENT_ID     = os.getenv('DISCORD_CLIENT_ID', '1494509191749042237')
CLIENT_SECRET = os.getenv('DISCORD_CLIENT_SECRET', '')
REDIRECT_URI  = os.getenv('DISCORD_REDIRECT_URI', 'https://omni-endpoint.crystal-kitsune-studios.com/callback')
GUILD_ID      = os.getenv('GUILD_ID', '')

OAUTH_URL = (
    'https://discord.com/api/oauth2/authorize'
    f'?client_id={CLIENT_ID}'
    f'&redirect_uri={requests.utils.quote(REDIRECT_URI, safe="")}'
    '&response_type=code&scope=identify+guilds'
)

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
    user = requests.get('https://discord.com/api/users/@me',
                        headers={'Authorization': f'Bearer {token}'}).json()
    if 'id' not in user:
        flash('Could not fetch user info.', 'danger')
        return redirect(url_for('login'))
    session['user'] = user
    session['token'] = token
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── Dashboard ─────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def index():
    conn = get_db()
    warn_count  = conn.execute('SELECT COUNT(*) FROM warnings').fetchone()[0]
    tag_count   = conn.execute('SELECT COUNT(*) FROM tags').fetchone()[0]
    log_count   = conn.execute('SELECT COUNT(*) FROM mod_logs').fetchone()[0]
    recent_logs = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 5').fetchall()
    conn.close()
    return render_template('index.html', user=session['user'],
        warn_count=warn_count, tag_count=tag_count,
        log_count=log_count, recent_logs=recent_logs)

# ── Mod Logs ──────────────────────────────────────────────────────────────

@app.route('/modlogs')
@login_required
def modlogs():
    conn = get_db()
    logs = conn.execute('SELECT * FROM mod_logs ORDER BY timestamp DESC LIMIT 200').fetchall()
    conn.close()
    return render_template('modlogs.html', user=session['user'], logs=logs)

# ── Tags / Commands ───────────────────────────────────────────────────────

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

@app.route('/commands/delete/<int:tag_id>', methods=['POST'])
@login_required
def delete_command(tag_id):
    conn = get_db()
    conn.execute('DELETE FROM tags WHERE id=?', (tag_id,))
    conn.commit()
    conn.close()
    flash('Tag deleted.', 'success')
    return redirect(url_for('commands'))

# ── AutoMod ───────────────────────────────────────────────────────────────

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
    spam  = 1 if request.form.get('automod_spam') else 0
    caps  = 1 if request.form.get('automod_caps') else 0
    inv   = 1 if request.form.get('automod_invites') else 0
    thresh= int(request.form.get('automod_spam_threshold', 5))
    ratio = float(request.form.get('automod_caps_ratio', 0.7))
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

# ── Settings ──────────────────────────────────────────────────────────────

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
