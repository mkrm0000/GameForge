import json
import time

import httpx

from events import emit


class LLMError(Exception):
    pass


class Truncated(LLMError):
    pass


def extract_json(text):
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < i:
        raise ValueError("No JSON object in response")
    return json.loads(text[i : j + 1])


class LLM:
    def __init__(self, cfg):
        self.cfg = cfg

    def _post(self, body):
        c = self.cfg
        if not c.get("base_url") or not c.get("model"):
            raise LLMError("Set base_url and model in the model config")
        headers = {"Authorization": f"Bearer {c['api_key']}"} if c.get("api_key") else {}
        try:
            return httpx.post(
                c["base_url"].rstrip("/") + "/chat/completions",
                json=body,
                headers=headers,
                timeout=300,
            )
        except httpx.HTTPError as e:
            raise LLMError(f"Connection failed: {type(e).__name__}: {e}")

    def chat(self, messages, json_schema=None):
        try:
            return self._chat(messages, json_schema)
        except LLMError as e:
            emit("error", str(e))
            raise

    def _chat(self, messages, json_schema):
        c = self.cfg
        messages = [dict(m) for m in messages]
        body = {
            "model": c.get("model"),
            "messages": messages,
            "temperature": c.get("temperature", 0.7),
            "max_tokens": c.get("max_tokens", 8000),
        }
        if json_schema:
            hint = "Respond with only a JSON object matching this JSON schema. No prose, no code fences.\n" + json.dumps(json_schema)
            if messages[0]["role"] == "system":
                messages[0]["content"] += "\n\n" + hint
            else:
                messages.insert(0, {"role": "system", "content": hint})
            body["response_format"] = {"type": "json_object"}
        emit("info", f"Request to {c.get('model')} ({len(messages)} messages, max_tokens {body['max_tokens']}{', JSON mode' if json_schema else ''})")
        t0 = time.time()
        r = self._post(body)
        if r.status_code == 400 and "response_format" in body:
            emit("info", "400 with response_format; retrying without it")
            del body["response_format"]
            r = self._post(body)
        if r.status_code >= 400:
            raise LLMError(f"Model API error {r.status_code}: {r.text[:300]}")
        try:
            data = r.json()
            if "error" in data:
                raise LLMError(f"Model API error: {str(data['error'])[:300]}")
            choice = data["choices"][0]
            text = choice["message"]["content"] or ""
        except (KeyError, IndexError, ValueError, TypeError):
            raise LLMError("Unexpected response shape from model API")
        emit(
            "assistant", text, model=data.get("model") or c.get("model"), ms=int((time.time() - t0) * 1000),
            tokens=(data.get("usage") or {}).get("completion_tokens"), finish=choice.get("finish_reason"),
        )
        if choice.get("finish_reason") == "length":
            raise Truncated(f"Model output hit max_tokens ({body['max_tokens']}); raise Max tokens in the model panel and press Save")
        return text

    def chat_json(self, messages, schema, validate=lambda d: d):
        messages = list(messages)
        for m in messages:
            emit(m["role"], m["content"])
        for attempt in range(2):
            raw = self.chat(messages, schema)
            try:
                return validate(extract_json(raw))
            except ValueError as e:
                if attempt:
                    msg = f"Model returned invalid JSON: {str(e)[:300]}"
                    emit("error", msg)
                    raise LLMError(msg)
                repair = f"Invalid: {str(e)[:300]}. Return only the corrected, complete JSON object."
                emit("error", f"Invalid output, retrying once: {str(e)[:300]}")
                emit("user", repair)
                messages += [{"role": "assistant", "content": raw}, {"role": "user", "content": repair}]