"""CV and cover letter builder: a master CV + a role description in, a tailored CV and a cover letter out.

The local model (core.llm, Ollama) does the writing; both documents are saved as
Word documents (.docx) in local_storage/cv/. Nothing leaves the machine. The master
CV is kept as master-cv.md there, so it only has to be given once.
"""
import io
import re
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.shared import Pt

from core import llm
from tools.files import _safe_path

CV_FOLDER = Path("local_storage") / "cv"
MASTER_NAME = "master-cv.md"
MAX_INPUT_CHARS = 20000  # per input; keeps both well inside the model's context window

CV_PROMPT = """You tailor a CV to a role. Rewrite the MASTER CV as a CV for the ROLE, in Markdown.

Rules:
- Use only facts that are in the master CV. Never invent employers, dates, titles, degrees, skills or numbers.
- Keep name, contact details, employers, titles, periods and education exactly as given.
- Write the profile summary for this role. Put the experience, bullets and skills that matter most for the role first, and shorten or drop what is irrelevant. Use the role's own wording where the master CV supports it.
- Language: write the whole CV in the language the ROLE description is written in, even if the master CV is in another language - translate the content (keep names, employers, titles of qualifications and technical terms as they are). Do not mention this.
- Layout: "# Name", a contact line, then the sections Profile, Experience, Education and Skills as "## " headings, with the heading words in that same language (leave out a section with nothing in it).
- Reply with the CV only."""

LETTER_PROMPT = """You write a cover letter for the ROLE from the candidate's MASTER CV, in plain text.

Rules:
- 3-4 short paragraphs, under 250 words: why this role and company, one or two concrete achievements from the master CV that match what the role asks for, a short closing.
- Use only facts that are in the master CV. Never invent achievements, numbers or experience; do not claim skills it does not show.
- Language: write the whole letter in the language the ROLE description is written in, even if the master CV is in another language - translate the facts you use.
- Start with a greeting in that language ("Dear <name>," if the role names a contact, else the equivalent of "Dear Hiring Manager,") and end with the equivalent of "Sincerely," and the candidate's name.
- Reply with the letter only."""


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "role"


MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # a .docx with photos is mostly image bytes; only its text is used
UPLOAD_TYPES = (".txt", ".md", ".docx")


def _read_docx(source) -> str:
    """Text of a .docx given a path or a file object."""
    return "\n".join(p.text for p in Document(source).paragraphs)


def read_upload(file_obj, filename: str) -> str:
    """Text of an uploaded .txt, .md or .docx (the web form). Raises ValueError with a message for the user."""
    name = str(filename or "")
    if not name.lower().endswith(UPLOAD_TYPES):
        raise ValueError(f"Unsupported file type: {name or '?'}. Choose a .txt, .md or .docx file.")
    data = file_obj.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise ValueError(f"{name} is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    try:
        if name.lower().endswith(".docx"):
            return _read_docx(io.BytesIO(data))
        return data.decode("utf-8")
    except Exception as e:  # a corrupt .docx raises a zip/XML error
        raise ValueError(f"Could not read {name} as text: {e}") from e


def _read_input(value: str):
    """(text, error) for an argument that is either the text itself or a project-relative .md/.txt/.docx file path."""
    value = str(value).strip()
    if "\n" in value or len(value) > 255:
        return value, None
    path, error = _safe_path(value)
    if error is None and path and Path(path).is_file():
        try:
            if path.lower().endswith(".docx"):
                return _read_docx(str(path)), None
            return Path(path).read_text(encoding="utf-8"), None
        except Exception:  # a corrupt .docx raises a zip/XML error, not just OSError
            return None, f"ERROR: could not read {value} as text. Pass a .md, .txt or .docx file, or paste the text."
    return value, None


def _add_runs(paragraph, text, size=None):
    """Add text to a paragraph, turning **bold** into bold runs."""
    for i, part in enumerate(re.split(r"\*\*(.+?)\*\*", text)):
        if part:
            run = paragraph.add_run(part)
            run.bold = i % 2 == 1 or None
            if size:
                run.font.size = Pt(size)


def _save_docx(markdown: str, path: Path) -> None:
    """Lay the model's light Markdown (# / ## headings, - bullets, **bold**, paragraphs) out as a Word document."""
    doc = Document()
    doc.styles["Normal"].font.name = "Calibri"
    doc.styles["Normal"].font.size = Pt(11)
    paragraph_lines = []

    def flush():
        if paragraph_lines:
            paragraph = doc.add_paragraph()
            for i, line in enumerate(paragraph_lines):
                if i:
                    paragraph.add_run().add_break()
                _add_runs(paragraph, line)
            paragraph_lines.clear()

    for line in markdown.splitlines():
        line = line.rstrip()
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        bullet = re.match(r"^\s*[-*•]\s+(.*)$", line)
        if heading:
            flush()
            doc.add_heading(heading.group(2).replace("**", ""), level=0 if heading.group(1) == "#" else 2)  # 0 is the Title style
        elif bullet:
            flush()
            _add_runs(doc.add_paragraph(style="List Bullet"), bullet.group(1))
        elif line.strip():
            paragraph_lines.append(line.strip())
        else:
            flush()
    flush()
    doc.save(str(path))


def _write(system: str, master: str, role: str) -> str:
    reply = llm.chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": f"MASTER CV:\n{master}\n\nROLE:\n{role}"},
        ],
        think=False,
    )
    return (reply.get("content") or "").strip()


def tailor(master: str | None, role: str, company: str | None = None):
    """(result, error): result is {"cv", "letter", "cv_path", "letter_path"}, error a message for the user.

    master and role are the texts themselves. A blank master falls back to the
    saved master-cv.md; a given one replaces it.
    """
    if not role or not str(role).strip():
        return None, "pass the role description (the job ad text, or a file with it)."

    saved = CV_FOLDER / MASTER_NAME
    if master and str(master).strip():
        master = str(master)
        if len(master) <= MAX_INPUT_CHARS:
            CV_FOLDER.mkdir(parents=True, exist_ok=True)
            saved.write_text(master, encoding="utf-8")
    elif saved.is_file():
        master = saved.read_text(encoding="utf-8")
    else:
        return None, "no master CV yet. Paste it, or upload a .txt, .md or .docx file."

    role_text = str(role)
    if len(master) > MAX_INPUT_CHARS or len(role_text) > MAX_INPUT_CHARS:
        return None, f"the master CV and the role description must each be under {MAX_INPUT_CHARS} characters."

    if company and str(company).strip():
        role_text = f"Company: {str(company).strip()}\n{role_text}"

    try:
        cv = _write(CV_PROMPT, master, role_text)
        letter = _write(LETTER_PROMPT, master, role_text)
    except llm.LLMError as e:
        return None, str(e)
    if not cv or not letter:
        return None, "the model returned an empty document. Try again."

    CV_FOLDER.mkdir(parents=True, exist_ok=True)
    # Microseconds so two runs in the same second don't overwrite each other
    stamp = f"{_slug(str(company or role_text.splitlines()[0])[:40])}_{datetime.now():%Y%m%d_%H%M%S_%f}"
    cv_path = CV_FOLDER / f"cv_{stamp}.docx"
    letter_path = CV_FOLDER / f"cover-letter_{stamp}.docx"
    _save_docx(cv, cv_path)
    _save_docx(letter, letter_path)
    return {"cv": cv, "letter": letter, "cv_path": cv_path, "letter_path": letter_path}, None


def tailor_application(master_cv=None, role=None, company=None, **kwargs):
    """Tool: a tailored CV and a cover letter from a master CV and a role description (each text or a project file)."""
    role = role or kwargs.get("job") or kwargs.get("job_description") or kwargs.get("role_description")
    master_cv = master_cv or kwargs.get("cv")

    texts = []
    for value in (master_cv, role):
        if value and str(value).strip():
            text, error = _read_input(value)
            if error:
                return error
            texts.append(text)
        else:
            texts.append(None)

    result, error = tailor(texts[0], texts[1], company)
    if error:
        return f"ERROR: {error}"
    return (
        f"Tailored CV saved to {result['cv_path']}\nCover letter saved to {result['letter_path']}"
        f"\n\n{result['cv']}\n\n---\n\n{result['letter']}"
    )
