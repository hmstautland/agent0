import difflib

def generate_diff(old, new):
    diff = difflib.unified_diff(
        old.splitlines(),
        new.splitlines(),
        lineterm="",
        fromfile="old",
        tofile="new"
    )
    return "\n".join(diff)