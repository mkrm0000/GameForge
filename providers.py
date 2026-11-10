import httpx

from llm import LLMError

PRESETS = {
    "openrouter": "https://openrouter.ai/api/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "gemini": "https://generativelanguage.googleapis.com/v1beta/openai",
    "deepseek": "https://api.deepseek.com/v1",
    "groq": "https://api.groq.com/openai/v1",
    "mistral": "https://api.mistral.ai/v1",
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "llamacpp": "http://localhost:8080/v1",
    "vllm": "http://localhost:8000/v1",
}

FAMILIES = {"claude": "anthropic/claude", "gemini": "google/gemini", "chatgpt": "openai/gpt", "deepseek": "deepseek/"}


def openrouter_models():
    try:
        r = httpx.get(PRESETS["openrouter"] + "/models", timeout=20)
        r.raise_for_status()
        models = sorted(r.json()["data"], key=lambda m: -(m.get("created") or 0))
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise LLMError(f"Could not load OpenRouter models: {type(e).__name__}: {e}")
    ids = [m["id"] for m in models if m.get("architecture", {}).get("output_modalities", ["text"]) == ["text"]]
    out = {f: [i for i in ids if i.startswith(p) and not i.endswith(":free")] for f, p in FAMILIES.items()}
    out["free"] = ["openrouter/free"] + [i for i in ids if i.endswith(":free")]
    return out
