import re
import shutil
from pathlib import Path

BUILTIN = Path(__file__).parent / "builtin_assets"
BUILTIN.mkdir(exist_ok=True)
NAME_RE = re.compile(r"(\w+) (\d+),(\d+) (\w+)\.\w+")


def list_assets():
    out = []
    for f in sorted(BUILTIN.iterdir()):
        if not f.is_file() or f.name.startswith("."):
            continue
        m = NAME_RE.fullmatch(f.name)
        out.append({"file": f.name, "shape": m[1], "size": f"{m[2]}x{m[3]}", "color": m[4]} if m else {"file": f.name})
    return out


def copy_to(project_dir):
    shutil.copytree(BUILTIN, project_dir / "assets" / "builtin", dirs_exist_ok=True)
