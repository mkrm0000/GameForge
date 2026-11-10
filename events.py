import threading
import time
from collections import deque

_events = deque(maxlen=500)
_lock = threading.Lock()
_last = 0


def emit(kind, text="", **meta):
    global _last
    with _lock:
        _last += 1
        _events.append({"id": _last, "t": time.strftime("%H:%M:%S"), "kind": kind, "text": text[:20000], **meta})


def since(after):
    with _lock:
        return [e for e in _events if e["id"] > after]


def last():
    return _last