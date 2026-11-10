import json
import re
import shutil
from pathlib import Path

BUILTIN = Path(__file__).parent / "builtin_assets"
BUILTIN.mkdir(exist_ok=True)
NAME_RE = re.compile(r"(\w+) (\d+),(\d+) (\w+)\.\w+")
LIST_NAME = "file_list.json"


def describe(f):
    m = NAME_RE.fullmatch(f.name)
    return {"file": f.name, "shape": m[1], "size": f"{m[2]}x{m[3]}", "color": m[4]} if m else {"file": f.name}


def scan(folder):
    if not folder.is_dir():
        return []
    return [describe(f) for f in sorted(folder.iterdir()) if f.is_file() and not f.name.startswith(".") and f.name != LIST_NAME]


def write_list(path, items):
    path.write_text(json.dumps(items, indent=1), "utf-8")


def main_list():
    """Regenerate builtin_assets/file_list.json from disk and return it."""
    items = scan(BUILTIN)
    write_list(BUILTIN / LIST_NAME, items)
    return items


def project_list(project_dir):
    """Regenerate <project>/file_list.json from assets/builtin/ and return it."""
    items = scan(project_dir / "assets" / "builtin")
    project_dir.mkdir(parents=True, exist_ok=True)
    write_list(project_dir / LIST_NAME, items)
    return items


def copy_selected(project_dir, names, available):
    """Copy only the chosen builtin files that exist in `available`. Returns the names actually copied."""
    ok = {a["file"] for a in available}
    dest = project_dir / "assets" / "builtin"
    copied = []
    for n in dict.fromkeys(names):
        if n not in ok or (dest / n).exists():
            continue
        dest.mkdir(parents=True, exist_ok=True)
        shutil.copy2(BUILTIN / n, dest / n)
        copied.append(n)
    return copied
