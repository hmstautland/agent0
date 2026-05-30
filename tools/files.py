import os
from core.diff import generate_diff
from core.permission import request_permission

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def get_project_structure():
    structure = {}

    for root, dirs, files in os.walk(BASE_DIR):
        rel_root = os.path.relpath(root, BASE_DIR)

        structure[rel_root] = files

    return structure

def search_files(keyword=None, query=None, keywords=None, **kwargs):
    # Accept multiple possible parameter names from LLM-decided arguments
    # 'keywords' may be a list or a string; 'keyword' and 'query' kept for backward compatibility
    term = None
    if keywords:
        # if keywords is a list, join with spaces, else use as string
        if isinstance(keywords, (list, tuple)):
            term = " ".join([str(k) for k in keywords if k])
        else:
            term = str(keywords)
    term = term or keyword or query

    if not term:
        return "No search term provided"

    matches = []

    for root, _, files in os.walk(BASE_DIR):
        for file in files:
            if term.lower() in file.lower():
                matches.append(os.path.join(root, file))

    return matches[:10]

def read_files(path):
    full_path = os.path.abspath(os.path.join(BASE_DIR, path))

    # Prevent escaping project folder
    if not full_path.startswith(BASE_DIR):
        return "Access denied"

    if not os.path.exists(full_path):
        return "File not found"

    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()

        return content[:10000]  # limit size
    except Exception as e:
        return str(e)
    
def summarize_files(path): 
    content = read_files(path)
    return content[:2000]

def write_file(path, content):
    full_path = ...

    if not full_path.startswith(BASE_DIR):
        return "Access denied"

    # read old content
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            old_content = f.read()
    except FileNotFoundError:
        old_content = ""

    diff = generate_diff(old_content, content)

    print("\n--- FILE CHANGE PREVIEW ---")
    print(diff[:2000])  # limit output

    approved = request_permission(
        "write_file",
        {"path": path},
        "high"
    )

    if not approved:
        return "Write cancelled"

    # backup
    with open(full_path + ".bak", "w", encoding="utf-8") as f:
        f.write(old_content)

    # write new
    with open(full_path, "w", encoding="utf-8") as f:
        f.write(content)

    return f"File updated: {path}"