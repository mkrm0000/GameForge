import json
import os
import re
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from builtin import copy_to, list_assets
from events import emit, last, since
from llm import LLM, LLMError, Truncated
from providers import PRESETS, openrouter_models
from schemas import (
    FILES_SCHEMA, AcceptReq, ConfigIn, DesignDoc, DesignReq, PatchReq, SlugReq,
    build_messages, design_messages, patch_messages,
)

load_dotenv()

ROOT = Path(__file__).parent
PROJECTS = ROOT / "projects"
CONFIG = ROOT / "config.json"
PROJECTS.mkdir(exist_ok=True)
REQUIRED = ["index.html", "style.css", "game.js", "assets/manifest.json"]
SLUG_RE = re.compile(r"[a-z0-9-]{1,60}")
JSON_AS_CODE = re.compile(r"<script[^>]*\.json|import[^;\n]*from\s*['\"][^'\"]*\.json|import\(\s*['\"][^'\"]*\.json")

app = FastAPI()


@app.middleware("http")
async def no_cache(request, call_next):
    resp = await call_next(request)
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.exception_handler(LLMError)
async def llm_error(_, e):
    return JSONResponse({"detail": str(e)}, 502)


def mask(key):
    if not key:
        return ""
    return key[:3] + "…" + key[-4:] if len(key) > 8 else "…"


def load_config():
    cfg = {
        "provider": "ollama",
        "base_url": os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
        "api_key": os.getenv("LLM_API_KEY", ""),
        "model": os.getenv("LLM_MODEL", ""),
        "temperature": 0.7,
        "max_tokens": 8000,
    }
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text("utf-8")))
    return cfg


def merged_config(inc):
    cur = load_config()
    cfg = inc.model_dump()
    if cfg["api_key"] is None or cfg["api_key"] == mask(cur["api_key"]):
        cfg["api_key"] = cur["api_key"]
    return cfg


def project_dir(slug):
    if not SLUG_RE.fullmatch(slug):
        raise HTTPException(400, "Invalid slug")
    return PROJECTS / slug


def load_project(slug):
    f = project_dir(slug) / "design.json"
    if not f.exists():
        raise HTTPException(404, "Unknown project")
    return json.loads(f.read_text("utf-8"))


def save_project(slug, data):
    d = project_dir(slug)
    d.mkdir(exist_ok=True)
    (d / "design.json").write_text(json.dumps(data, indent=1), "utf-8")


def require_accepted(slug):
    p = load_project(slug)
    if not p.get("accepted"):
        raise HTTPException(403, "Design not accepted")
    return p


def valid_rel(rel):
    p = Path(rel)
    return bool(rel) and not p.is_absolute() and ".." not in p.parts and "\\" not in rel and rel != "design.json"


def write_file(slug, rel, content):
    f = project_dir(slug) / rel
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(content, "utf-8")


def parse_files(data):
    files = data.get("files") if isinstance(data, dict) else None
    if not isinstance(files, dict):
        raise ValueError('Expected {"files": {path: content}}')
    for rel, content in files.items():
        if not valid_rel(rel) or not isinstance(content, str):
            raise ValueError(f"Invalid file entry: {rel}")
    return files


def parse_build(data):
    files = parse_files(data)
    missing = [r for r in REQUIRED if r not in files]
    if missing:
        raise ValueError(f"Missing required files: {', '.join(missing)}")
    if any(JSON_AS_CODE.search(c) for c in files.values()):
        raise ValueError("JSON files must not be loaded as a script or module; manifest.json is data only")
    return files


def line(**kw):
    return json.dumps(kw) + "\n"


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower())[:30].strip("-") or "game"


@app.post("/api/design")
def design(req: DesignReq):
    if not req.idea.strip():
        raise HTTPException(400, "Idea is required")
    if req.settings.prototype:
        req.settings.audio = "None"
    slug = req.slug or f"{slugify(req.idea)}-{uuid.uuid4().hex[:6]}"
    project_dir(slug)
    doc = LLM(load_config()).chat_json(design_messages(req), DesignDoc.model_json_schema(), DesignDoc.model_validate)
    save_project(slug, {"request": req.model_dump(exclude={"slug"}), "design": doc.model_dump(), "accepted": False})
    emit("info", f"Design saved ({slug}): {doc.title}")
    return {"slug": slug, "design": doc.model_dump()}


@app.post("/api/accept")
def accept(req: AcceptReq):
    p = load_project(req.slug)
    p.update(design=req.design.model_dump(), accepted=True)
    save_project(req.slug, p)
    emit("info", f"Design accepted ({req.slug})")
    return {"slug": req.slug}


@app.post("/api/build")
def build(req: SlugReq):
    p = require_accepted(req.slug)
    proto = p["request"]["settings"].get("prototype")

    def stream():
        try:
            emit("info", f"Build started ({req.slug})")
            yield line(log="Generating game files...")
            files = LLM(load_config()).chat_json(build_messages(p["design"], p["request"], list_assets()), FILES_SCHEMA, parse_build)
            for rel, content in files.items():
                write_file(req.slug, rel, content)
                emit("info", f"Wrote {rel} ({len(content)} chars)")
                yield line(log=f"Wrote {rel}")
            if proto:
                copy_to(project_dir(req.slug))
                yield line(log="Copied builtin assets")
            elif not (project_dir(req.slug) / "music" / "README.md").exists():
                write_file(req.slug, "music/README.md", "Music generation is not implemented yet.\n")
            emit("info", f"Build finished: /play/{req.slug}/")
            yield line(done=True, slug=req.slug, play_url=f"/play/{req.slug}/")
        except (LLMError, OSError, ValueError) as e:
            emit("error", f"Build failed: {e}")
            yield line(error=str(e))

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@app.post("/api/patch")
def patch(req: PatchReq):
    p = require_accepted(req.slug)
    root = project_dir(req.slug)
    current = {}
    for rel in req.files:
        if not valid_rel(rel):
            raise HTTPException(400, f"Invalid path: {rel}")
        if not (root / rel).is_file():
            raise HTTPException(404, f"No such file: {rel}")
        current[rel] = (root / rel).read_text("utf-8")
    files = LLM(load_config()).chat_json(patch_messages(p["design"], current, req.instruction, p["request"]["settings"].get("prototype")), FILES_SCHEMA, parse_files)
    updated = {rel: c for rel, c in files.items() if rel in current}
    for rel, content in updated.items():
        write_file(req.slug, rel, content)
    emit("info", f"Patched: {', '.join(updated) or 'nothing changed'}")
    return {"updated": list(updated)}


@app.get("/api/events")
def get_events(after: int = 0):
    return {"events": since(after), "last": last()}


@app.get("/api/presets")
def presets():
    return PRESETS


@app.get("/api/openrouter-models")
def or_models():
    return openrouter_models()


@app.get("/api/config")
def get_config():
    c = load_config()
    c["api_key"] = mask(c["api_key"])
    return c


@app.post("/api/config")
def set_config(inc: ConfigIn):
    c = merged_config(inc)
    CONFIG.write_text(json.dumps(c, indent=1), "utf-8")
    emit("info", f"Config saved: {c['provider']} / {c['model']}")
    return {**c, "api_key": mask(c["api_key"])}


@app.post("/api/test-model")
def test_model(inc: ConfigIn | None = None):
    cfg = merged_config(inc) if inc else load_config()
    try:
        reply = LLM({**cfg, "max_tokens": 64}).chat([{"role": "user", "content": "Reply with OK"}])
        return {"ok": True, "reply": reply.strip()[:80]}
    except Truncated:
        return {"ok": True, "reply": "reached the model (token limit hit, likely a reasoning model)"}
    except LLMError as e:
        return {"ok": False, "error": str(e)}


app.mount("/play", StaticFiles(directory=PROJECTS, html=True), name="play")
app.mount("/", StaticFiles(directory=ROOT / "static", html=True), name="static")