from __future__ import annotations

import json
import os
import re
import sqlite3
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, url_for
from werkzeug.utils import secure_filename

from intelligence import analyze_document, answer_from_text, extract_text

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("LIFE_ADMIN_DATA", BASE_DIR / "data")).resolve()
UPLOAD_DIR = DATA_DIR / "documents"
DB_PATH = DATA_DIR / "life_admin.sqlite3"
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "tif", "tiff", "txt", "md"}
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "20"))

app = Flask(__name__)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "local-dev-change-me"), MAX_CONTENT_LENGTH=MAX_UPLOAD_MB * 1024 * 1024)
DATA_DIR.mkdir(parents=True, exist_ok=True)
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
 id TEXT PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL DEFAULT 'Other',
 original_name TEXT NOT NULL, stored_name TEXT NOT NULL, mime_type TEXT,
 extracted_text TEXT NOT NULL DEFAULT '', summary TEXT NOT NULL DEFAULT '',
 issue_date TEXT, expiry_date TEXT, due_date TEXT, amount REAL,
 tags TEXT NOT NULL DEFAULT '[]', pii TEXT NOT NULL DEFAULT '[]',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_expiry ON documents(expiry_date);
CREATE INDEX IF NOT EXISTS idx_documents_due ON documents(due_date);
CREATE INDEX IF NOT EXISTS idx_documents_category ON documents(category);
CREATE TABLE IF NOT EXISTS reminders (
 id INTEGER PRIMARY KEY AUTOINCREMENT, document_id TEXT NOT NULL,
 kind TEXT NOT NULL, remind_on TEXT NOT NULL, dismissed INTEGER NOT NULL DEFAULT 0,
 UNIQUE(document_id, kind, remind_on),
 FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

def connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn

def init_db():
    with connect() as db:
        db.executescript(SCHEMA)

def row_dict(row):
    if row is None: return None
    d = dict(row)
    for key in ("tags", "pii"):
        try: d[key] = json.loads(d.get(key) or "[]")
        except (TypeError, json.JSONDecodeError): d[key] = []
    return d

def get_doc(doc_id):
    with connect() as db:
        return row_dict(db.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone())

def all_docs():
    with connect() as db:
        rows = db.execute("SELECT * FROM documents ORDER BY updated_at DESC").fetchall()
    return [row_dict(r) for r in rows]

def sync_reminders(db, doc_id, expiry_date, due_date):
    db.execute("DELETE FROM reminders WHERE document_id=?", (doc_id,))
    for kind, raw in (("expiry", expiry_date), ("bill", due_date)):
        if not raw: continue
        try: target = date.fromisoformat(raw)
        except ValueError: continue
        remind_on = (target - timedelta(days=30 if kind == "expiry" else 7)).isoformat()
        db.execute("INSERT OR IGNORE INTO reminders(document_id,kind,remind_on) VALUES(?,?,?)", (doc_id, kind, remind_on))

def dashboard_data():
    docs = all_docs()
    today = date.today()
    upcoming = []
    overdue = []
    expiring = 0
    bills = 0
    for d in docs:
        for field, kind, label in (("expiry_date","expiry","Expires"),("due_date","bill","Due")):
            raw = d.get(field)
            if not raw: continue
            try: target = date.fromisoformat(raw)
            except ValueError: continue
            item = {**d, "date":raw, "kind":kind, "event_label":label, "days":(target-today).days}
            if target < today: overdue.append(item)
            elif target <= today + timedelta(days=60): upcoming.append(item)
            if kind=="expiry" and 0 <= (target-today).days <= 30: expiring += 1
            if kind=="bill" and 0 <= (target-today).days <= 30: bills += 1
    upcoming.sort(key=lambda x:x["date"])
    overdue.sort(key=lambda x:x["date"])
    total_size = sum(p.stat().st_size for p in UPLOAD_DIR.iterdir() if p.is_file())
    return {"total":len(docs),"expiring":expiring,"bills":bills,"upcoming":upcoming[:8],"overdue":overdue[:6],"storage_mb":round(total_size/1048576,1),
            "categories":category_counts(docs)}

def category_counts(docs):
    counts={}
    for d in docs: counts[d["category"]]=counts.get(d["category"],0)+1
    return sorted(counts.items(),key=lambda x:(-x[1],x[0]))

def allowed_file(filename):
    return "." in filename and filename.rsplit(".",1)[1].lower() in ALLOWED_EXTENSIONS

def search_docs(query, category="All"):
    docs=all_docs()
    q=query.strip().lower()
    out=[]
    for d in docs:
        if category!="All" and d["category"]!=category: continue
        hay=" ".join([d["title"],d["category"],d["original_name"]," ".join(d["tags"]),d["extracted_text"]]).lower()
        if not q or q in hay: out.append(d)
    return out

@app.route("/")
def dashboard():
    data=dashboard_data()
    return render_template("dashboard.html", data=data, active="dashboard")

@app.route("/documents")
def documents():
    query=request.args.get("q","")
    category=request.args.get("category","All")
    docs=search_docs(query,category)
    cats=sorted({d["category"] for d in all_docs()})
    return render_template("documents.html", docs=docs, categories=cats, selected_category=category, query=query, active="documents")

@app.route("/upload",methods=["POST"])
def upload():
    f=request.files.get("file")
    if not f or not f.filename:
        flash("Choose a document to upload.","error"); return redirect(url_for("documents"))
    if not allowed_file(f.filename):
        flash("Unsupported file type. Use PDF, image, TXT or Markdown.","error"); return redirect(url_for("documents"))
    original=secure_filename(f.filename) or "document"
    ext=Path(original).suffix.lower()
    doc_id=uuid.uuid4().hex
    stored=f"{doc_id}{ext}"
    path=UPLOAD_DIR/stored
    f.save(path)
    try:
        text=extract_text(path, ext)
        info=analyze_document(text, original)
        title=request.form.get("title","").strip() or info["suggested_title"] or Path(original).stem.replace("_"," ").title()
        category=request.form.get("category","").strip() or info["category"]
        tags=info["tags"]
        now=datetime.now().isoformat(timespec="seconds")
        with connect() as db:
            db.execute("""INSERT INTO documents(id,title,category,original_name,stored_name,mime_type,extracted_text,summary,issue_date,expiry_date,due_date,amount,tags,pii,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(doc_id,title,category,original,stored,f.mimetype,text,info["summary"],info["issue_date"],info["expiry_date"],info["due_date"],info["amount"],json.dumps(tags),json.dumps(info["pii"]),now,now))
            sync_reminders(db,doc_id,info["expiry_date"],info["due_date"])
        flash("Document added. Text and metadata were analyzed locally where supported.","success")
        return redirect(url_for("document_detail",doc_id=doc_id))
    except Exception as exc:
        path.unlink(missing_ok=True)
        app.logger.exception("Upload processing failed")
        flash(f"Could not process document: {exc}","error")
        return redirect(url_for("documents"))

@app.route("/documents/<doc_id>")
def document_detail(doc_id):
    d=get_doc(doc_id)
    if not d: abort(404)
    return render_template("detail.html",doc=d,active="documents")

@app.route("/documents/<doc_id>/file")
def document_file(doc_id):
    d=get_doc(doc_id)
    if not d: abort(404)
    path=UPLOAD_DIR/d["stored_name"]
    if not path.exists(): abort(404)
    return send_file(path,download_name=d["original_name"],as_attachment=request.args.get("download")=="1")

@app.route("/documents/<doc_id>/edit",methods=["POST"])
def edit_document(doc_id):
    d=get_doc(doc_id)
    if not d: abort(404)
    title=request.form.get("title","").strip()
    category=request.form.get("category","Other").strip() or "Other"
    expiry=request.form.get("expiry_date","").strip() or None
    due=request.form.get("due_date","").strip() or None
    issue=request.form.get("issue_date","").strip() or None
    amount=request.form.get("amount","").strip()
    tags=[x.strip() for x in request.form.get("tags","").split(",") if x.strip()]
    try:
        for val in (expiry,due,issue):
            if val: date.fromisoformat(val)
        amount_val=float(amount) if amount else None
        if amount_val is not None and amount_val<0: raise ValueError("Amount cannot be negative.")
        if not title: raise ValueError("Title is required.")
    except ValueError as exc:
        flash(str(exc),"error"); return redirect(url_for("document_detail",doc_id=doc_id))
    with connect() as db:
        db.execute("UPDATE documents SET title=?,category=?,issue_date=?,expiry_date=?,due_date=?,amount=?,tags=?,updated_at=? WHERE id=?",
                   (title,category,issue,expiry,due,amount_val,json.dumps(tags),datetime.now().isoformat(timespec="seconds"),doc_id))
        sync_reminders(db,doc_id,expiry,due)
    flash("Document details updated.","success")
    return redirect(url_for("document_detail",doc_id=doc_id))

@app.route("/documents/<doc_id>/delete",methods=["POST"])
def delete_document(doc_id):
    d=get_doc(doc_id)
    if not d: abort(404)
    with connect() as db: db.execute("DELETE FROM documents WHERE id=?",(doc_id,))
    (UPLOAD_DIR/d["stored_name"]).unlink(missing_ok=True)
    flash("Document deleted.","success"); return redirect(url_for("documents"))

@app.route("/ask",methods=["POST"])
def ask():
    question=request.form.get("question","").strip()
    if not question:
        flash("Enter a question first.","error"); return redirect(url_for("dashboard"))
    docs=all_docs()
    # Lightweight retrieval: rank by token overlap; avoid sending data anywhere unless API is explicitly configured.
    tokens={t for t in re.findall(r"[a-z0-9]{3,}",question.lower())}
    ranked=[]
    for d in docs:
        body=(d["title"]+" "+d["category"]+" "+d["extracted_text"]).lower()
        score=sum(1 for t in tokens if t in body)
        if score: ranked.append((score,d))
    ranked.sort(key=lambda x:(-x[0],x[1]["updated_at"]))
    chosen=[d for _,d in ranked[:4]]
    if not chosen:
        answer="I couldn't find matching information in your indexed documents. Try using a name, provider, document type, or exact phrase."
    else:
        context="\n\n".join(f"DOCUMENT: {d['title']}\nCATEGORY: {d['category']}\nTEXT:\n{d['extracted_text'][:5000]}" for d in chosen)
        answer=answer_from_text(question,context)
    return render_template("answer.html",question=question,answer=answer,sources=chosen,active="dashboard")

@app.route("/privacy")
def privacy():
    return render_template("privacy.html",active="privacy")

@app.route("/api/summary")
def api_summary():
    return jsonify(dashboard_data())

@app.errorhandler(413)
def too_large(_):
    flash(f"File is too large. Maximum upload size is {MAX_UPLOAD_MB} MB.","error")
    return redirect(url_for("documents"))

init_db()
if __name__=="__main__":
    app.run(host=os.environ.get("HOST","127.0.0.1"),port=int(os.environ.get("PORT","5000")),debug=False)
