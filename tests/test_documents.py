import pytest
from docx import Document

import agent as agent_mod
import tools.documents as documents
import tools.skills as skills
from core.llm import LLMError
from tools.registry import TOOLS


@pytest.fixture
def folder(monkeypatch, tmp_path):
    monkeypatch.setattr(documents, "CV_FOLDER", tmp_path)
    return tmp_path


def stub_llm(monkeypatch):
    """Replaces llm.chat: the CV prompt gets "CV for <role>", the letter prompt "Letter for <role>"."""
    calls = []

    def chat(messages, **kwargs):
        calls.append(messages)
        kind = "CV" if messages[0]["content"] == documents.CV_PROMPT else "Letter"
        return {"content": f"{kind} for {messages[1]['content'].split('ROLE:', 1)[1].strip()}"}

    monkeypatch.setattr(documents.llm, "chat", chat)
    return calls


def test_tailors_a_cv_and_a_cover_letter_from_master_and_role(monkeypatch, folder):
    calls = stub_llm(monkeypatch)

    result = documents.tailor_application(master_cv="# Ada\n- Built X", role="Data analyst\nPython", company="Acme")

    cv = "\n".join(p.text for p in Document(str(next(folder.glob("cv_acme_*.docx")))).paragraphs)
    letter = "\n".join(p.text for p in Document(str(next(folder.glob("cover-letter_acme_*.docx")))).paragraphs)
    assert "CV for Company: Acme" in cv and "Data analyst" in cv
    assert letter.startswith("Letter for")
    assert "Tailored CV saved to" in result and "Cover letter saved to" in result
    assert all("# Ada" in c[1]["content"] for c in calls)


def test_docx_layout_has_headings_bullets_and_bold(tmp_path):
    path = tmp_path / "a.docx"

    documents._save_docx("# Ada\n\nada@x.no | Oslo\n\n## Experience\n\n**Engineer, Acme** (2020)\n\n- Built X\n- Cut Y\n\nSincerely,\nAda", path)

    paragraphs = Document(str(path)).paragraphs
    assert [(p.style.name, p.text) for p in paragraphs] == [
        ("Title", "Ada"), ("Normal", "ada@x.no | Oslo"), ("Heading 2", "Experience"),
        ("Normal", "Engineer, Acme (2020)"), ("List Bullet", "Built X"), ("List Bullet", "Cut Y"),
        ("Normal", "Sincerely,\nAda"),
    ]
    assert paragraphs[3].runs[0].bold


def test_master_cv_is_remembered_for_the_next_request(monkeypatch, folder):
    calls = stub_llm(monkeypatch)
    documents.tailor_application(master_cv="# Ada\n- Built X", role="Role one")

    documents.tailor_application(role="Role two")

    assert (folder / documents.MASTER_NAME).read_text() == "# Ada\n- Built X"
    assert "# Ada" in calls[-1][1]["content"]


def test_master_cv_and_role_can_be_project_files(monkeypatch, folder):
    calls = stub_llm(monkeypatch)
    monkeypatch.setattr(documents, "_safe_path", lambda p: (str(folder / p), None))
    (folder / "me.md").write_text("# Ada from file")
    (folder / "job.txt").write_text("Role from file")

    documents.tailor_application(master_cv="me.md", role="job.txt")

    assert "# Ada from file" in calls[0][1]["content"] and "Role from file" in calls[0][1]["content"]


def test_master_cv_can_be_a_word_file(monkeypatch, folder):
    calls = stub_llm(monkeypatch)
    monkeypatch.setattr(documents, "_safe_path", lambda p: (str(folder / p), None))
    word = Document()
    word.add_paragraph("Ada from Word")
    word.save(str(folder / "me.docx"))

    documents.tailor_application(master_cv="me.docx", role="Analyst")

    assert "Ada from Word" in calls[0][1]["content"]


def test_asks_for_missing_input_instead_of_writing(monkeypatch, folder):
    calls = stub_llm(monkeypatch)

    assert documents.tailor_application(master_cv="# Ada").startswith("ERROR: pass the role description")
    assert documents.tailor_application(role="Analyst").startswith("ERROR: no master CV yet")
    assert not calls and not list(folder.glob("cv_*"))


def test_model_failure_is_returned_not_raised(monkeypatch, folder):
    def chat(messages, **kwargs):
        raise LLMError("Could not reach Ollama")

    monkeypatch.setattr(documents.llm, "chat", chat)

    assert documents.tailor_application(master_cv="# Ada", role="Analyst") == "ERROR: Could not reach Ollama"
    assert not list(folder.glob("cv_*"))


def test_tool_is_registered_low_risk_and_the_skill_names_it():
    assert TOOLS["tailor_application"]["risk"] == "low"
    assert "tailor_application" in skills.load_skill(name="cv-and-cover-letter")


def test_cv_and_cover_letter_requests_skip_the_local_first_step():
    for text in ("build a CV", "write a cover letter for a data analyst job", "Please create my resume", "tailor my CV to this job"):
        assert agent_mod.tool_route(text) == agent_mod.OLLAMA_MODEL
    assert agent_mod.tool_route("what is a cover letter") is None


def test_both_prompts_follow_the_language_of_the_role_description():
    for prompt in (documents.CV_PROMPT, documents.LETTER_PROMPT):
        assert "language the ROLE description is written in" in prompt
