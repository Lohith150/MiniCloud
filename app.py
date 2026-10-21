import os
import uuid
import secrets
from pathlib import Path as FilePath

from flask import (
    Flask, request, redirect, url_for, render_template_string,
    send_from_directory, flash, abort
)
from flask_login import (
    LoginManager, UserMixin, login_user, logout_user,
    login_required, current_user
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = FilePath(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get(
    "MINICLOUD_SECRET_KEY", "change-this-secret-key-for-local-use"
)
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{BASE_DIR / 'minicloud.db'}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024  # 100 MB per upload

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"

STORAGE_LIMIT = 1024 * 1024 * 1024  # 1 GB


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    files = db.relationship("StoredFile", backref="owner", lazy=True)
    folders = db.relationship("Folder", backref="owner", lazy=True)


class Folder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True)


class StoredFile(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=False)
    size_bytes = db.Column(db.Integer, nullable=False, default=0)
    folder_id = db.Column(db.Integer, db.ForeignKey("folder.id"), nullable=True)



class ShareLink(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    file_id = db.Column(db.Integer, db.ForeignKey("stored_file.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, index=True)
    token = db.Column(db.String(100), unique=True, nullable=False, index=True)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=db.func.current_timestamp())
    password_hash = db.Column(db.String(255), nullable=True)
    expires_at = db.Column(db.DateTime, nullable=True)
    max_downloads = db.Column(db.Integer, nullable=True)
    download_count = db.Column(db.Integer, nullable=False, default=0)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def format_size(size):
    size = float(size or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return f"{size:.1f} GB"


def file_category(filename):
    ext = FilePath(filename).suffix.lower()
    if ext in {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}:
        return "image"
    if ext in {".pdf", ".doc", ".docx", ".txt", ".rtf", ".odt"}:
        return "document"
    if ext in {".mp4", ".mov", ".avi", ".mkv"}:
        return "video"
    if ext in {".mp3", ".wav", ".ogg", ".m4a"}:
        return "audio"
    if ext in {".zip", ".rar", ".7z", ".tar", ".gz"}:
        return "archive"
    return "file"


def owned_folder(folder_id):
    if not folder_id:
        return None
    folder = db.session.get(Folder, int(folder_id))
    if not folder or folder.user_id != current_user.id:
        abort(404)
    return folder


def breadcrumbs(folder):
    result = []
    while folder:
        result.append(folder)
        folder = db.session.get(Folder, folder.parent_id) if folder.parent_id else None
    return list(reversed(result))


PAGE = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MiniCloud</title>
<style>
:root{--bg:#f4f7fb;--card:#fff;--text:#172033;--muted:#687386;--blue:#4263eb;--line:#e5eaf2;--green:#12805c}
*{box-sizing:border-box}body{margin:0;background:var(--bg);font-family:Inter,Segoe UI,Arial,sans-serif;color:var(--text)}
a{color:inherit;text-decoration:none}.layout{display:flex;min-height:100vh}.sidebar{width:245px;background:#fff;border-right:1px solid var(--line);padding:24px 16px;flex-shrink:0}
.brand{font-size:22px;font-weight:800;margin:0 8px 32px;color:#263b9b}.nav a{display:block;padding:12px 13px;border-radius:10px;margin:5px 0;color:#475269}.nav a:hover,.nav a.active{background:#edf1ff;color:#2848cc;font-weight:700}
.storage{margin:28px 6px 18px;padding:15px;border:1px solid var(--line);border-radius:14px}.storage strong{display:block;margin-bottom:8px}.bar{height:7px;background:#e8ecf5;border-radius:20px;overflow:hidden}.bar span{display:block;height:100%;background:var(--blue)}.small{font-size:12px;color:var(--muted);margin-top:8px}
.logout{display:block;margin:16px 8px;color:#687386}.main{flex:1;min-width:0;padding:34px clamp(18px,4vw,56px);max-width:1400px}.topline{display:flex;align-items:center;justify-content:space-between;gap:16px;flex-wrap:wrap}.eyebrow{color:var(--blue);font-size:13px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}h1{font-size:32px;margin:7px 0}h2{font-size:19px;margin:0 0 7px}.muted{color:var(--muted)}.account{font-size:13px;color:var(--muted);background:#fff;border:1px solid var(--line);border-radius:20px;padding:9px 13px}
.hero{margin:25px 0 20px;padding:26px;border-radius:20px;background:linear-gradient(120deg,#253b9c,#5676f5);color:#fff;display:flex;justify-content:space-between;align-items:center;gap:18px;flex-wrap:wrap}.hero h2{font-size:23px}.hero p{color:#e0e6ff;margin:8px 0 0}.btn{border:0;border-radius:10px;padding:11px 15px;background:var(--blue);color:#fff;font-weight:700;cursor:pointer;font-size:14px;display:inline-block}.btn:hover{filter:brightness(.96)}.btn.white{background:#fff;color:#2848cc}.btn.light{background:#edf1ff;color:#2848cc}.btn.danger{background:#fff0f0;color:#b42318}.stats{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:18px 0 28px}.stat,.panel{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:20px}.stat .label{font-size:13px;color:var(--muted)}.stat strong{font-size:24px;display:block;margin-top:8px}
.panel{margin:18px 0}.panel-head{display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:15px}.form-row{display:flex;gap:10px;flex-wrap:wrap}.input{border:1px solid #d9e0ec;border-radius:10px;padding:11px 12px;font:inherit;background:#fff;min-width:0}.input[type=text],.input[type=email],.input[type=password]{width:min(100%,360px)}input[type=file]{max-width:100%;padding:10px;border:1px dashed #c5cede;border-radius:10px;background:#fafbff;flex:1;min-width:220px}
.folder-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:12px}.folder-card{border:1px solid var(--line);border-radius:13px;padding:15px;background:#fff}.folder-icon{font-size:25px}.folder-card strong{display:block;margin:8px 0}.folder-card .muted{font-size:12px}.crumbs{margin:15px 0;color:var(--muted);font-size:14px}.crumbs a{color:#3555d8}.file-list{display:flex;flex-direction:column;gap:9px}.file-row{display:flex;align-items:center;gap:12px;border:1px solid var(--line);border-radius:12px;padding:13px;background:#fff;flex-wrap:wrap}.file-icon{width:42px;height:42px;display:grid;place-items:center;background:#f0f3ff;border-radius:10px;font-size:20px;flex-shrink:0}.file-info{flex:1;min-width:120px}.file-info strong{display:block;overflow-wrap:anywhere}.file-info span{font-size:12px;color:var(--muted)}.actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.actions .btn{padding:8px 10px;font-size:12px}.empty{text-align:center;padding:25px;color:var(--muted)}.flash{padding:12px 14px;border-radius:10px;background:#eaf8f0;color:#12633e;margin:12px 0}.flash.error{background:#fff0f0;color:#a82020}.upload-help{font-size:12px;color:var(--muted);margin-top:10px}
.share-settings{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin-top:7px;flex-basis:100%}
.share-settings .input{max-width:190px;width:100%;font-size:12px;padding:8px}
.progress-wrap{display:none;margin-top:12px;background:#e8ecf5;border-radius:20px;height:9px;overflow:hidden}
.progress-bar{height:100%;width:0;background:var(--blue);transition:width .15s}
.progress-label{display:none;font-size:12px;color:var(--muted);margin-top:6px}
.stat{box-shadow:0 3px 12px rgba(20,35,80,.03)}
.file-row:hover,.folder-card:hover{border-color:#c8d2ff;box-shadow:0 3px 12px rgba(20,35,80,.04)}
.btn:disabled{opacity:.5;cursor:not-allowed}
.auth-wrap{min-height:100vh;display:grid;place-items:center;padding:20px}.auth-card{background:#fff;padding:30px;border:1px solid var(--line);border-radius:18px;width:min(100%,420px)}.auth-card form{display:grid;gap:12px}.auth-card .input{width:100%}
@media(max-width:760px){.layout{display:block}.sidebar{width:100%;padding:15px}.brand{margin-bottom:12px}.nav{display:flex;flex-wrap:wrap}.nav a{padding:9px}.storage{margin:12px 5px}.main{padding:22px 14px}.stats{grid-template-columns:1fr}.hero{padding:20px}h1{font-size:27px}}
</style>
</head>
<body>
{% if not current_user.is_authenticated %}
<div class="auth-wrap"><div class="auth-card">
<div class="brand" style="margin:0 0 18px">☁ MiniCloud</div>
<h1 style="font-size:27px">{{ 'Create your account' if page == 'signup' else 'Welcome back' }}</h1>
<p class="muted">Your personal space for every file.</p>
{% with messages = get_flashed_messages() %}{% for message in messages %}<div class="flash">{{ message }}</div>{% endfor %}{% endwith %}
<form method="post" action="{{ url_for('signup' if page == 'signup' else 'login') }}">
<input class="input" type="email" name="email" placeholder="Email address" required>
<input class="input" type="password" name="password" placeholder="Password (at least 6 characters)" required>
<button class="btn" type="submit">{{ 'Create account' if page == 'signup' else 'Log in' }}</button>
</form>
<p class="muted">{{ 'Already registered?' if page == 'signup' else 'New to MiniCloud?' }} <a style="color:#3555d8;font-weight:700" href="{{ url_for('login' if page == 'signup' else 'signup') }}">{{ 'Log in' if page == 'signup' else 'Create an account' }}</a></p>
</div></div>
{% else %}
<div class="layout">
<aside class="sidebar">
<div class="brand">☁ MiniCloud</div>
<nav class="nav">
<a class="{{ 'active' if not current_folder else '' }}" href="{{ url_for('home') }}">▦ &nbsp; My files</a>
<a href="{{ url_for('home', folder_id=current_folder.id if current_folder else '') }}#upload">↑ &nbsp; Upload files</a>
<a href="{{ url_for('home', folder_id=current_folder.id if current_folder else '') }}#folders">📁 &nbsp; Folders</a>
</nav>
<div class="storage"><strong>☁ Storage</strong><div>{{ used_text }} of 1 GB used</div><div class="bar" style="margin-top:10px"><span style="width:{{ storage_percent }}%"></span></div><div class="small">Demo storage limit</div></div>
<a class="logout" href="{{ url_for('logout') }}">↪ Log out</a>
</aside>
<main class="main">
<div class="topline"><div><div class="eyebrow">Personal cloud storage</div><h1>{{ current_folder.name if current_folder else 'My files' }}</h1><div class="muted">Your personal space for every file.</div></div><div class="account">{{ current_user.email }}<br><span class="small">Personal account</span></div></div>
{% with messages = get_flashed_messages(with_categories=true) %}{% for category, message in messages %}<div class="flash {{ 'error' if category == 'error' else '' }}">{{ message }}</div>{% endfor %}{% endwith %}
<div class="hero"><div><h2>Your files, all in one place.</h2><p>Create folders and organize files.</p></div><a class="btn white" href="#upload">＋ Upload a file</a></div>
<div class="stats">
<div class="stat"><div class="label">Total files</div><strong>{{ total_files }}</strong></div>
<div class="stat"><div class="label">Storage used</div><strong>{{ used_text }}</strong></div>
<div class="stat"><div class="label">Available storage</div><strong>{{ available_text }}</strong></div>
</div>
<div class="panel" id="folders">
<div class="panel-head"><div><h2>📁 Folders</h2><div class="muted">Create folders to organize files</div></div></div>
<form method="post" action="{{ url_for('create_folder') }}" class="form-row">
<input type="hidden" name="parent_id" value="{{ current_folder.id if current_folder else '' }}">
<input class="input" type="text" name="folder_name" placeholder="Folder name (e.g. College Projects)" maxlength="120" required>
<button class="btn" type="submit">＋ Create folder</button>
</form>
<div class="crumbs"><a href="{{ url_for('home') }}">My files</a>{% for crumb in crumbs %} › <a href="{{ url_for('home', folder_id=crumb.id) }}">{{ crumb.name }}</a>{% endfor %}</div>
{% if folders %}
<div class="folder-grid">{% for folder in folders %}
<div class="folder-card"><div class="folder-icon">📁</div><strong>{{ folder.name }}</strong><div class="muted">Folder</div><div style="margin-top:12px;display:flex;gap:7px;flex-wrap:wrap"><a class="btn light" href="{{ url_for('home', folder_id=folder.id) }}">Open folder</a><form method="post" action="{{ url_for('delete_folder', folder_id=folder.id) }}" onsubmit="return confirm('Delete this folder and all files/subfolders inside it? This cannot be undone.')"><button class="btn danger" type="submit">Delete folder</button></form></div></div>
{% endfor %}</div>
{% else %}<div class="empty">No folders here yet. Create your first folder above.</div>{% endif %}
</div>
<div class="panel" id="upload">
<div class="panel-head"><div><h2>Upload a file</h2><div class="muted">Upload into: <strong>{{ current_folder.name if current_folder else 'My files (root)' }}</strong></div></div></div>
<form id="upload-form" method="post" action="{{ url_for('upload_file') }}" enctype="multipart/form-data">
<input type="hidden" name="folder_id" value="{{ current_folder.id if current_folder else '' }}">
<div class="form-row">
<input class="input" type="file" name="file" id="file" required>
<button class="btn" type="submit">↑ Upload file</button>
</div>
<div class="upload-help">Maximum 100 MB per file. Select a file first, then click Upload file.</div>
<div class="progress-wrap" id="progress-wrap"><div class="progress-bar" id="progress-bar"></div></div>
<div class="progress-label" id="progress-label">Uploading… 0%</div>
</form>
</div>
<div class="panel">
<div class="panel-head"><div><h2>▦ Files</h2><div class="muted">Files in this folder</div></div><input class="input" id="search" type="text" placeholder="Search files..." style="max-width:260px"></div>
{% if files %}
<div class="file-list" id="file-list">{% for file in files %}
<div class="file-row" data-name="{{ file.original_name|lower }}" data-category="{{ file.category }}">
<div class="file-icon">{{ '🖼️' if file.category == 'image' else '📄' if file.category == 'document' else '🎬' if file.category == 'video' else '🎵' if file.category == 'audio' else '📦' if file.category == 'archive' else '📁' }}</div>
<div class="file-info"><strong>{{ file.original_name }}</strong><span>{{ file.size_text }} · {{ file.category|title }}</span></div>
<div class="actions">
{% if file.category == 'image' %}<a class="btn light" href="{{ url_for('preview_file', file_id=file.id) }}" target="_blank">Preview</a>{% endif %}
<a class="btn light" href="{{ url_for('download_file', file_id=file.id) }}">Download</a>
<form method="post" action="{{ url_for('share_file', file_id=file.id) }}" style="flex-basis:100%">
<button class="btn light" type="submit">{{ 'Update share settings' if file.share_url else 'Share' }}</button>
<div class="share-settings">
<input class="input" type="password" name="share_password" placeholder="Optional link password" autocomplete="new-password">
<select class="input" name="expiry_hours" aria-label="Link expiry">
<option value="0">No expiry</option><option value="24">Expires in 24 hours</option><option value="168">Expires in 7 days</option><option value="720">Expires in 30 days</option>
</select>
<input class="input" type="number" name="max_downloads" min="1" max="10000" placeholder="Download limit (optional)">
</div>
</form>
<form method="post" action="{{ url_for('revoke_share', file_id=file.id) }}" onsubmit="return confirm('Revoke this share link?')"><button class="btn danger" type="submit" {% if not file.share_url %}disabled{% endif %}>Revoke</button></form>
{% if file.share_url %}<div style="flex-basis:100%;display:flex;gap:7px;flex-wrap:wrap;margin-top:6px"><input class="input share-url" type="text" readonly value="{{ file.share_url }}" style="flex:1;min-width:180px"><button class="btn light copy-share" type="button">Copy link</button></div><div class="upload-help" style="flex-basis:100%">{{ file.share_details }}</div>{% endif %}
<form method="post" action="{{ url_for('delete_file', file_id=file.id) }}" onsubmit="return confirm('Delete this file?')"><button class="btn danger" type="submit">Delete</button></form>
</div>
</div>
{% endfor %}</div>
{% else %}<div class="empty">No files in this folder yet. Choose a file above and click Upload file.</div>{% endif %}
</div>
</main></div>
<script>
const searchInput=document.getElementById('search');
if(searchInput){searchInput.addEventListener('input',()=>{const q=searchInput.value.toLowerCase();document.querySelectorAll('.file-row').forEach(row=>{row.style.display=row.dataset.name.includes(q)?'flex':'none';});});}
document.querySelectorAll('.copy-share').forEach(button=>{button.addEventListener('click',async()=>{const field=button.parentElement.querySelector('.share-url');try{await navigator.clipboard.writeText(field.value);button.textContent='Copied!';}catch(error){field.focus();field.select();const copied=document.execCommand('copy');button.textContent=copied?'Copied!':'Select and copy';}});});
const uploadForm=document.getElementById('upload-form');
if(uploadForm){uploadForm.addEventListener('submit',event=>{
  const fileInput=document.getElementById('file');
  if(!fileInput.files.length){return;}
  const file=fileInput.files[0];
  if(file.size>100*1024*1024){return;}
  event.preventDefault();
  const data=new FormData(uploadForm), xhr=new XMLHttpRequest();
  const wrap=document.getElementById('progress-wrap'), bar=document.getElementById('progress-bar'), label=document.getElementById('progress-label');
  wrap.style.display='block';label.style.display='block';
  const button=uploadForm.querySelector('button[type=submit]');button.disabled=true;button.textContent='Uploading…';
  xhr.upload.addEventListener('progress',e=>{if(e.lengthComputable){const pct=Math.round(e.loaded/e.total*100);bar.style.width=pct+'%';label.textContent='Uploading… '+pct+'%';}});
  xhr.addEventListener('load',()=>{if(xhr.status>=200&&xhr.status<400){window.location.href=xhr.responseURL||window.location.href;}else{label.textContent='Upload failed. Please try again.';button.disabled=false;button.textContent='↑ Upload file';}});
  xhr.addEventListener('error',()=>{label.textContent='Upload failed. Check your connection and try again.';button.disabled=false;button.textContent='↑ Upload file';});
  xhr.open('POST',uploadForm.action);xhr.send(data);
});}
</script>
{% endif %}
</body></html>
"""


def render_home(page="home"):
    if not current_user.is_authenticated:
        return render_template_string(PAGE, page=page)
    folder_id = request.args.get("folder_id", type=int)
    current_folder = owned_folder(folder_id) if folder_id else None
    folders_query = Folder.query.filter_by(user_id=current_user.id, parent_id=folder_id)
    folders = folders_query.order_by(Folder.name.asc()).all()
    file_query = StoredFile.query.filter_by(user_id=current_user.id, folder_id=folder_id)
    stored_files = file_query.order_by(StoredFile.original_name.asc()).all()

    # Refresh recorded sizes when files exist on disk.
    changed = False
    for item in StoredFile.query.filter_by(user_id=current_user.id).all():
        path = UPLOAD_DIR / item.stored_name
        if path.is_file() and item.size_bytes != path.stat().st_size:
            item.size_bytes = path.stat().st_size
            changed = True
    if changed:
        db.session.commit()

    all_files = StoredFile.query.filter_by(user_id=current_user.id).all()
    used = sum(f.size_bytes or 0 for f in all_files)
    display_files = []
    for item in stored_files:
        display_files.append({
            "id": item.id,
            "original_name": item.original_name,
            "size_text": format_size(item.size_bytes),
            "category": file_category(item.original_name),
            "share_url": (
                url_for("shared_file", token=active_share.token, _external=True)
                if (active_share := ShareLink.query.filter_by(
                    file_id=item.id, user_id=current_user.id, active=True
                ).first())
                else None
            ),
            "share_details": (
                "Password protected" if active_share.password_hash else "No password"
            ) + (
                (" · expires " + active_share.expires_at.strftime("%Y-%m-%d %H:%M UTC"))
                if active_share and active_share.expires_at else ""
            ) + (
                (" · " + str(active_share.download_count) + "/" + str(active_share.max_downloads) + " downloads")
                if active_share and active_share.max_downloads else ""
            ) if active_share else "",
        })
    return render_template_string(
        PAGE,
        page=page,
        current_folder=current_folder,
        crumbs=breadcrumbs(current_folder),
        folders=folders,
        files=display_files,
        total_files=len(all_files),
        used_text=format_size(used),
        available_text=format_size(max(0, STORAGE_LIMIT - used)),
        storage_percent=min(100, round((used / STORAGE_LIMIT) * 100, 2)),
    )


@app.route("/")
@login_required
def home():
    return render_home()


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or len(password) < 6:
            flash("Enter a valid email and a password of at least 6 characters.", "error")
            return render_home("signup")
        if User.query.filter_by(email=email).first():
            flash("An account with that email already exists.", "error")
            return render_home("signup")
        user = User(email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash("Account created successfully.")
        return redirect(url_for("home"))
    return render_home("signup")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            login_user(user)
            return redirect(url_for("home"))
        flash("Incorrect email or password.", "error")
    return render_home("login")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("login"))


@app.route("/folders/create", methods=["POST"])
@login_required
def create_folder():
    name = request.form.get("folder_name", "").strip()
    parent_value = request.form.get("parent_id", "").strip()
    parent_id = int(parent_value) if parent_value.isdigit() else None
    if parent_id:
        owned_folder(parent_id)
    if not name or "/" in name or "\\" in name:
        flash("Enter a folder name without slashes.", "error")
        return redirect(url_for("home", folder_id=parent_id) + "#folders")
    duplicate = Folder.query.filter_by(user_id=current_user.id, parent_id=parent_id, name=name).first()
    if duplicate:
        flash("A folder with that name already exists here.", "error")
        return redirect(url_for("home", folder_id=parent_id) + "#folders")
    db.session.add(Folder(user_id=current_user.id, name=name, parent_id=parent_id))
    db.session.commit()
    flash(f"Folder '{name}' created.")
    return redirect(url_for("home", folder_id=parent_id) + "#folders")


@app.route("/folders/<int:folder_id>/delete", methods=["POST"])
@login_required
def delete_folder(folder_id):
    folder = owned_folder(folder_id)
    parent_id = folder.parent_id

    # Delete the selected folder and every nested folder, file record, and share link.
    folder_ids = []
    pending = [folder.id]
    while pending:
        current_id = pending.pop()
        folder_ids.append(current_id)
        children = Folder.query.filter_by(user_id=current_user.id, parent_id=current_id).all()
        pending.extend(child.id for child in children)

    items = StoredFile.query.filter(
        StoredFile.user_id == current_user.id,
        StoredFile.folder_id.in_(folder_ids),
    ).all()
    for item in items:
        ShareLink.query.filter_by(file_id=item.id, user_id=current_user.id).delete(synchronize_session=False)
        try:
            stored_path = UPLOAD_DIR / item.stored_name
            if stored_path.exists():
                stored_path.unlink()
        except OSError:
            app.logger.exception("Could not remove stored file while deleting folder")
        db.session.delete(item)

    Folder.query.filter(
        Folder.user_id == current_user.id,
        Folder.id.in_(folder_ids),
    ).delete(synchronize_session=False)
    db.session.commit()
    flash("Folder and its contents deleted.")
    return redirect(url_for("home", folder_id=parent_id) + "#folders")


@app.route("/upload", methods=["POST"])
@login_required
def upload_file():
    uploaded = request.files.get("file")
    folder_value = request.form.get("folder_id", "").strip()
    folder_id = int(folder_value) if folder_value.isdigit() else None
    if folder_id:
        owned_folder(folder_id)
    if not uploaded or not uploaded.filename:
        flash("Please choose a file before clicking Upload file.", "error")
        return redirect(url_for("home", folder_id=folder_id) + "#upload")
    safe_name = secure_filename(uploaded.filename)
    if not safe_name:
        flash("That filename is not valid. Please choose another file.", "error")
        return redirect(url_for("home", folder_id=folder_id) + "#upload")
    current_used = sum(
        f.size_bytes or 0 for f in StoredFile.query.filter_by(user_id=current_user.id).all()
    )
    uploaded.stream.seek(0, os.SEEK_END)
    file_size = uploaded.stream.tell()
    uploaded.stream.seek(0)
    if file_size > 100 * 1024 * 1024:
        flash("The maximum file size is 100 MB.", "error")
        return redirect(url_for("home", folder_id=folder_id) + "#upload")
    if current_used + file_size > STORAGE_LIMIT:
        flash("Your 1 GB storage limit would be exceeded.", "error")
        return redirect(url_for("home", folder_id=folder_id) + "#upload")
    stored_name = f"{uuid.uuid4().hex}_{safe_name}"
    destination = UPLOAD_DIR / stored_name
    try:
        uploaded.save(destination)
        record = StoredFile(
            user_id=current_user.id,
            stored_name=stored_name,
            original_name=safe_name,
            size_bytes=file_size,
            folder_id=folder_id,
        )
        db.session.add(record)
        db.session.commit()
    except Exception:
        db.session.rollback()
        if destination.exists():
            destination.unlink()
        app.logger.exception("File upload failed")
        flash("Upload failed. Please try again.", "error")
        return redirect(url_for("home", folder_id=folder_id) + "#upload")
    flash(f"'{safe_name}' uploaded successfully.")
    return redirect(url_for("home", folder_id=folder_id))


@app.route("/preview/<int:file_id>")
@login_required
def preview_file(file_id):
    item = db.session.get(StoredFile, file_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    if file_category(item.original_name) != "image":
        abort(415)
    return send_from_directory(UPLOAD_DIR, item.stored_name, mimetype=None, as_attachment=False)


@app.route("/download/<int:file_id>")
@login_required
def download_file(file_id):
    item = db.session.get(StoredFile, file_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    return send_from_directory(
        UPLOAD_DIR, item.stored_name, as_attachment=True,
        download_name=item.original_name
    )


def share_is_available(share):
    from datetime import datetime, timezone
    if not share or not share.active:
        return False
    # Store timestamps as naive UTC for compatibility with SQLite DateTime.
    now = datetime.utcnow()
    if share.expires_at and now >= share.expires_at:
        return False
    if share.max_downloads is not None and share.download_count >= share.max_downloads:
        return False
    return True


@app.route("/share/<int:file_id>", methods=["POST"])
@login_required
def share_file(file_id):
    from datetime import datetime, timedelta
    item = db.session.get(StoredFile, file_id)
    if not item or item.user_id != current_user.id:
        abort(404)

    share = ShareLink.query.filter_by(
        file_id=item.id, user_id=current_user.id, active=True
    ).first()
    if share is None:
        share = ShareLink(
            file_id=item.id,
            user_id=current_user.id,
            token=secrets.token_urlsafe(32),
            active=True,
            download_count=0,
        )
        db.session.add(share)

    raw_password = request.form.get("share_password", "").strip()
    share.password_hash = generate_password_hash(raw_password) if raw_password else None
    expiry_hours = request.form.get("expiry_hours", "0")
    try:
        expiry_hours = int(expiry_hours)
    except (TypeError, ValueError):
        expiry_hours = 0
    if expiry_hours in (24, 168, 720):
        share.expires_at = datetime.utcnow() + timedelta(hours=expiry_hours)
    else:
        share.expires_at = None

    raw_limit = request.form.get("max_downloads", "").strip()
    try:
        limit = int(raw_limit) if raw_limit else None
    except ValueError:
        limit = None
    share.max_downloads = limit if limit and 1 <= limit <= 10000 else None
    share.download_count = 0
    db.session.commit()
    flash("Share link is ready. Copy it from the file row.")
    return redirect(url_for("home", folder_id=item.folder_id))


@app.route("/share/<int:file_id>/revoke", methods=["POST"])
@login_required
def revoke_share(file_id):
    item = db.session.get(StoredFile, file_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    ShareLink.query.filter_by(
        file_id=item.id, user_id=current_user.id, active=True
    ).update({"active": False})
    db.session.commit()
    flash("Share link revoked. The old link will no longer work.")
    return redirect(url_for("home", folder_id=item.folder_id))


SHARED_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Shared file - MiniCloud</title>
<style>body{font-family:Arial,sans-serif;background:#f4f7fb;color:#172033;display:grid;place-items:center;min-height:100vh;margin:0;padding:20px}
.card{background:white;border:1px solid #e5eaf2;border-radius:16px;padding:28px;max-width:520px;width:100%;overflow-wrap:anywhere}
.btn{display:inline-block;background:#4263eb;color:white;text-decoration:none;padding:12px 16px;border:0;border-radius:9px;font-weight:bold;cursor:pointer}
.input{display:block;width:100%;box-sizing:border-box;padding:12px;margin:12px 0;border:1px solid #d9e0ec;border-radius:9px}
.muted{color:#687386}.flash{color:#a82020}</style></head><body>
<main class="card"><h1>☁ MiniCloud</h1><h2>{{ filename }}</h2>
<p class="muted">Someone has shared this file with you.</p>
{% if password_required %}<p>This share link requires a password.</p>{% endif %}
{% if error %}<p class="flash">{{ error }}</p>{% endif %}
<form method="post" action="{{ url_for('download_shared_file', token=token) }}">
{% if password_required %}<input class="input" type="password" name="password" placeholder="Enter share password" required>{% endif %}
<button class="btn" type="submit">Download file</button></form></main></body></html>"""


@app.route("/s/<token>")
def shared_file(token):
    share = ShareLink.query.filter_by(token=token, active=True).first()
    if not share or not share_is_available(share):
        abort(404)
    item = db.session.get(StoredFile, share.file_id)
    if not item or not (UPLOAD_DIR / item.stored_name).is_file():
        abort(404)
    return render_template_string(
        SHARED_PAGE,
        filename=item.original_name,
        token=token,
        password_required=bool(share.password_hash),
        error=None,
    )


@app.route("/s/<token>/download", methods=["POST"])
def download_shared_file(token):
    share = ShareLink.query.filter_by(token=token, active=True).first()
    if not share or not share_is_available(share):
        abort(404)
    item = db.session.get(StoredFile, share.file_id)
    if not item or not (UPLOAD_DIR / item.stored_name).is_file():
        abort(404)
    if share.password_hash:
        password = request.form.get("password", "")
        if not password or not check_password_hash(share.password_hash, password):
            return render_template_string(
                SHARED_PAGE,
                filename=item.original_name,
                token=token,
                password_required=True,
                error="Incorrect password. Please try again.",
            ), 403
    share.download_count = (share.download_count or 0) + 1
    db.session.commit()
    return send_from_directory(
        UPLOAD_DIR, item.stored_name, as_attachment=True,
        download_name=item.original_name,
    )


@app.route("/delete/<int:file_id>", methods=["POST"])
@login_required
def delete_file(file_id):
    item = db.session.get(StoredFile, file_id)
    if not item or item.user_id != current_user.id:
        abort(404)
    path = UPLOAD_DIR / item.stored_name
    ShareLink.query.filter_by(file_id=item.id).delete(synchronize_session=False)
    db.session.delete(item)
    db.session.commit()
    if path.is_file():
        path.unlink()
    flash(f"'{item.original_name}' deleted.")
    return redirect(url_for("home"))


@app.route("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(413)
def too_large(_error):
    flash("The selected file is too large. Maximum size is 100 MB.", "error")
    if current_user.is_authenticated:
        return redirect(url_for("home") + "#upload")
    return redirect(url_for("login"))


def initialize_database():
    with app.app_context():
        db.create_all()
        # Add new columns to an existing database without deleting user data.
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if "stored_file" in tables:
            columns = {col["name"] for col in inspector.get_columns("stored_file")}
            with db.engine.begin() as connection:
                if "size_bytes" not in columns:
                    connection.execute(text("ALTER TABLE stored_file ADD COLUMN size_bytes INTEGER NOT NULL DEFAULT 0"))
                if "folder_id" not in columns:
                    connection.execute(text("ALTER TABLE stored_file ADD COLUMN folder_id INTEGER"))
        # Add advanced sharing columns safely to existing databases.
        inspector = inspect(db.engine)
        tables = inspector.get_table_names()
        if "share_link" in tables:
            share_columns = {col["name"] for col in inspector.get_columns("share_link")}
            additions = {
                "password_hash": "VARCHAR(255)",
                "expires_at": "DATETIME",
                "max_downloads": "INTEGER",
                "download_count": "INTEGER NOT NULL DEFAULT 0",
            }
            with db.engine.begin() as connection:
                for column_name, column_type in additions.items():
                    if column_name not in share_columns:
                        connection.execute(text(
                            f"ALTER TABLE share_link ADD COLUMN {column_name} {column_type}"
                        ))
        # Keep stored file sizes accurate after a code update.
        for item in StoredFile.query.all():
            path = UPLOAD_DIR / item.stored_name
            if path.is_file():
                item.size_bytes = path.stat().st_size
        db.session.commit()


initialize_database()

if __name__ == "__main__":
    print("MiniCloud is starting at http://127.0.0.1:5000")
    app.run(host="127.0.0.1", port=5000, debug=False)
