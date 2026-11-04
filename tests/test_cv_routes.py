import io

import core.auth as auth_mod
import tools.documents as documents
from docx import Document
from fastapi.testclient import TestClient

from core.ui import app


def _logged_in_client(monkeypatch, tmp_path):
    monkeypatch.setattr(auth_mod, "PASSWORD", "testpass")
    monkeypatch.setattr(documents, "CV_FOLDER", tmp_path)
    client = TestClient(app)
    client.post("/login", data={"password": "testpass"})
    return client


def _stub_llm(monkeypatch):
    seen = []

    def chat(messages, **kwargs):
        seen.append(messages[1]["content"])
        return {"content": "Letter" if messages[0]["content"] == documents.LETTER_PROMPT else "# Ada\n\n## Profile\n\nText"}

    monkeypatch.setattr(documents.llm, "chat", chat)
    return seen


def _docx(text):
    buffer = io.BytesIO()
    word = Document()
    word.add_paragraph(text)
    word.save(buffer)
    return buffer.getvalue()


def test_tailor_from_pasted_text_returns_previews_and_downloadable_docx(monkeypatch, tmp_path):
    client = _logged_in_client(monkeypatch, tmp_path)
    seen = _stub_llm(monkeypatch)

    data = client.post("/cv/tailor", data={"master_text": "I am Ada", "role_text": "Analyst", "company": "Acme"}).json()

    assert data["letter"] == "Letter" and data["cv"].startswith("# Ada")
    assert "I am Ada" in seen[0] and "Analyst" in seen[0]
    download = client.get(data["cv_url"])
    assert download.status_code == 200
    assert Document(io.BytesIO(download.content)).paragraphs[0].text == "Ada"


def test_tailor_from_uploaded_files_wins_over_the_text_boxes(monkeypatch, tmp_path):
    client = _logged_in_client(monkeypatch, tmp_path)
    seen = _stub_llm(monkeypatch)

    response = client.post(
        "/cv/tailor",
        data={"master_text": "ignored", "role_text": ""},
        files={"master_file": ("cv.docx", _docx("Ada from Word")), "role_file": ("job.md", b"Job from file")},
    )

    assert response.status_code == 200
    assert "Ada from Word" in seen[0] and "Job from file" in seen[0] and "ignored" not in seen[0]


def test_tailor_rejects_missing_input_and_unsupported_files(monkeypatch, tmp_path):
    client = _logged_in_client(monkeypatch, tmp_path)
    _stub_llm(monkeypatch)

    missing = client.post("/cv/tailor", data={"master_text": "Ada", "role_text": ""})
    bad_type = client.post("/cv/tailor", data={"role_text": "x"}, files={"master_file": ("cv.pdf", b"%PDF")})

    assert missing.status_code == 400 and "role description" in missing.json()["error"]
    assert bad_type.status_code == 400 and "Unsupported file type" in bad_type.json()["error"]


def test_only_generated_docx_files_can_be_downloaded(monkeypatch, tmp_path):
    client = _logged_in_client(monkeypatch, tmp_path)
    (tmp_path / "master-cv.md").write_text("private")

    assert client.get("/cv/files/master-cv.md").status_code == 404
    # An encoded slash doesn't reach the route (the catch-all page answers), so never a file
    assert "attachment" not in client.get("/cv/files/..%2Fagent0.db").headers.get("content-disposition", "")
    assert client.get("/cv/files/cv_a_20260101_000000_000000.docx").status_code == 404


def test_cv_routes_require_login(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "CV_FOLDER", tmp_path)

    response = TestClient(app).post("/cv/tailor", data={"role_text": "x"}, follow_redirects=False)

    assert response.status_code == 303
