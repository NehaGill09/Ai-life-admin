import io
import app as life

def test_dashboard_and_upload_txt(tmp_path,monkeypatch):
    monkeypatch.setattr(life,"DATA_DIR",tmp_path)
    monkeypatch.setattr(life,"UPLOAD_DIR",tmp_path/"documents")
    monkeypatch.setattr(life,"DB_PATH",tmp_path/"test.sqlite3")
    life.UPLOAD_DIR.mkdir()
    life.init_db()
    client=life.app.test_client()
    response=client.get("/")
    assert response.status_code==200
    text=b"Passport record\nIssue date: 2025-01-01\nExpiry date: 2027-01-01\nContact neha@example.com"
    response=client.post("/upload",data={"file":(io.BytesIO(text),"passport.txt")},content_type="multipart/form-data",follow_redirects=True)
    assert response.status_code==200
    assert b"Passport" in response.data
    docs=life.all_docs()
    assert len(docs)==1
    assert docs[0]["category"]=="Identity"
    assert client.get("/documents").status_code==200
    assert client.post("/ask",data={"question":"When does passport expire?"}).status_code==200

def test_upload_rejects_unsupported(tmp_path,monkeypatch):
    monkeypatch.setattr(life,"DATA_DIR",tmp_path)
    monkeypatch.setattr(life,"UPLOAD_DIR",tmp_path/"documents")
    monkeypatch.setattr(life,"DB_PATH",tmp_path/"test.sqlite3")
    life.UPLOAD_DIR.mkdir()
    life.init_db()
    client=life.app.test_client()
    response=client.post("/upload",data={"file":(io.BytesIO(b"bad"),"x.exe")},content_type="multipart/form-data",follow_redirects=True)
    assert response.status_code==200
    assert b"Unsupported file type" in response.data
