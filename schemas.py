import json

from pydantic import BaseModel, Field


class Guides(BaseModel):
    dimension: str = "2D"
    art_style: str = "Pixel"
    platform: str = "PC"
    perspective: str = "Top-down"
    controls: list[str] = ["Keyboard"]
    genre: str = "Auto"
    renderer: str = "Canvas 2D"
    length: str = "Short demo"


class Settings(BaseModel):
    audio: str = "SFX only"
    progression: str = "Single level"
    difficulty: str = "Normal"
    session: str = "~5 min"
    performance: str = "Standard"
    palette: str = "Auto"
    prototype: bool = False


class DesignReq(BaseModel):
    idea: str = Field(min_length=1)
    notes: str = ""
    guides: Guides = Guides()
    settings: Settings = Settings()
    slug: str | None = None


class Asset(BaseModel):
    name: str
    type: str
    description: str


class DesignDoc(BaseModel):
    title: str
    pitch: str
    genre: str
    core_loop: str
    controls: str
    entities: list[str]
    mechanics: list[str]
    win_lose: str
    assets: list[Asset]
    audio_plan: str
    file_tree: list[str]
    impl_notes: str


class SlugReq(BaseModel):
    slug: str


class AcceptReq(BaseModel):
    slug: str
    design: DesignDoc


class PatchReq(BaseModel):
    slug: str
    instruction: str = Field(min_length=1)
    files: list[str] = Field(min_length=1)


class ConfigIn(BaseModel):
    provider: str = "custom"
    base_url: str
    api_key: str | None = None
    model: str
    temperature: float = Field(0.7, ge=0, le=2)
    max_tokens: int = Field(8000, ge=1)


FILES_SCHEMA = {
    "type": "object",
    "properties": {"files": {"type": "object", "additionalProperties": {"type": "string"}}},
    "required": ["files"],
}

DESIGN_SYS = (
    "You are a game designer. Output only JSON. Keep the whole design under 400 words. "
    "The game is a small browser game in plain HTML/CSS/JS with procedural art. "
    "Where a guide or setting is 'Auto', choose what fits the idea. "
    "controls is a single string; file_tree lists relative paths."
)

BUILD_SYS = (
    "You are a senior game developer. Implement the approved design as a complete, playable browser game. "
    'Output only JSON: {"files": {"<relative path>": "<content>"}}. '
    "Required files: index.html, style.css, game.js, assets/manifest.json. "
    "Split game.js into ES modules (script type=module) if it exceeds ~300 lines. "
    "index.html must reference style.css and game.js by relative path. "
    "Draw all art procedurally (canvas drawing or small inline SVG); no external downloads, no base64 blobs, no binary files. "
    "If the renderer is Three.js, import it from https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.module.js. "
    "assets/manifest.json is a plain data file listing the assets: never load it with a script tag or import, and the game must not depend on it. Do not create music files; if audio is enabled, synthesize SFX with WebAudio in code. "
    "Honor the chosen controls, platform (add touch controls for mobile), renderer, difficulty, session length, palette and performance. "
    "Include a start screen with brief instructions and a restart option. The game must run without errors when served from a subfolder."
)

PATCH_SYS = (
    "You edit an existing browser game. You get the design, the current content of the listed files and an instruction. "
    'Output only JSON: {"files": {"<path>": "<full new content>"}} with only the listed files that must change. '
    "Never include unchanged files."
)


SELECT_SCHEMA = {
    "type": "object",
    "properties": {"assets": {"type": "array", "items": {"type": "string"}}},
    "required": ["assets"],
}

SELECT_SYS = (
    "You pick builtin assets for a browser game. You get the task, the assets already in the project (project list) "
    "and the assets available to add (main list). "
    'Output only JSON: {"assets": ["<file name from the main list>"]}. '
    "Choose only files from the main list, copied exactly, that the task really needs and that are not already in the project. "
    "Return an empty list if nothing fits; the game will then use plain geometry. Never invent file names. "
    "Names that parse as '<shape> <w>,<h> <color>.<ext>' are described by shape, size and color; other files are listed by name only."
)

ASSET_BUILD = (
    " Builtin assets: the user message lists the assets copied into assets/builtin/ (project list). "
    "Load them from there with encodeURI because names contain spaces and commas, and use them where they fit. "
    "Anything not in the list must be drawn procedurally (canvas geometry or CSS shapes); never reference a file that is not listed. "
    "assets/manifest.json lists only the builtin assets actually used."
)

ASSET_PATCH = (
    " The user message lists the assets in assets/builtin/ (project list). Use only those or canvas/CSS geometry; "
    "never reference an unlisted file."
)

PROTOTYPE_DESIGN = (
    " PROTOTYPE MODE: no art or audio assets. Use only simple geometry or the builtin assets; "
    "assets lists only those and audio_plan is 'none'."
)

PROTOTYPE_BUILD = (
    " PROTOTYPE MODE overrides the art and audio rules above: no generated art and no audio of any kind (no WebAudio, no music, no SFX). "
    "Use only the builtin assets listed in the user message, loaded from assets/builtin/ with encodeURI because names contain spaces and commas, "
    "or simple canvas geometry (rect, arc, line) and CSS shapes. If the list is empty, use geometry only. No SVG sprites. "
    "Names that parse as '<shape> <w>,<h> <color>.<ext>' are described by shape, size and color; other files (fonts etc.) are listed by name. "
    "assets/manifest.json lists only the builtin assets actually used."
)

PROTOTYPE_PATCH = " PROTOTYPE MODE: no audio and no generated art; use only assets/builtin or canvas geometry."


def design_messages(req):
    return [
        {"role": "system", "content": DESIGN_SYS + (PROTOTYPE_DESIGN if req.settings.prototype else "")},
        {
            "role": "user",
            "content": f"Idea: {req.idea.strip()}\nNotes: {req.notes.strip() or 'none'}\n"
            f"Guides: {json.dumps(req.guides.model_dump())}\nSettings: {json.dumps(req.settings.model_dump())}",
        },
    ]


def select_messages(design, task, main, project, prototype=False):
    sys = SELECT_SYS + (" PROTOTYPE MODE: no art or audio generation, so prefer builtin assets over geometry where they fit." if prototype else "")
    return [
        {"role": "system", "content": sys},
        {
            "role": "user",
            "content": f"Task: {task}\nDesign:\n{json.dumps(design)}\n"
            f"Project list (already in the project): {json.dumps(project)}\nMain list (available to add): {json.dumps(main)}",
        },
    ]


def build_messages(design, request, project_assets):
    proto = request.get("settings", {}).get("prototype")
    ctx = {k: request.get(k) for k in ("notes", "guides", "settings")}
    user = (
        f"Design:\n{json.dumps(design)}\nGuides and settings:\n{json.dumps(ctx)}\n"
        f"Project list (in assets/builtin/): {json.dumps(project_assets)}"
    )
    return [
        {"role": "system", "content": BUILD_SYS + ASSET_BUILD + (PROTOTYPE_BUILD if proto else "")},
        {"role": "user", "content": user},
    ]


def patch_messages(design, files, instruction, project_assets, prototype=False):
    return [
        {"role": "system", "content": PATCH_SYS + ASSET_PATCH + (PROTOTYPE_PATCH if prototype else "")},
        {
            "role": "user",
            "content": f"Design:\n{json.dumps(design)}\nInstruction: {instruction}\n"
            f"Project list (in assets/builtin/): {json.dumps(project_assets)}\nFiles:\n{json.dumps(files)}",
        },
    ]