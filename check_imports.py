import ast
import sys
from pathlib import Path

stdlib = set(getattr(sys, "stdlib_module_names", ()))
imports = set()

for path in Path(".").rglob("*.py"):
    if any(part in {"venv", ".venv", "__pycache__", ".git"} for part in path.parts):
        continue

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except Exception as e:
        print(f"Could not parse {path}: {e}")
        continue

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            if node.level == 0:
                imports.add(node.module.split(".")[0])

missing = []

for name in sorted(imports):
    if name in stdlib or name in {"__future__"}:
        continue

    try:
        __import__(name)
        print(f"OK       {name}")
    except Exception as e:
        missing.append((name, str(e)))
        print(f"MISSING  {name} ({e})")

print("\nSummary:")
if missing:
    print("Imports that failed:")
    for name, error in missing:
        print(f"  {name}: {error}")
    sys.exit(1)
else:
    print("All discovered imports loaded successfully.")