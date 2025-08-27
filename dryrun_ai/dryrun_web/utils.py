# utils.py
from typing import Any, Dict, Tuple

SAFE_REPR_MAX = 160

def safe_repr(val: Any, max_len: int = SAFE_REPR_MAX) -> str:
    try:
        s = repr(val)
    except Exception:
        s = f"<unrepr {type(val).__name__}>"
    if len(s) > max_len:
        s = s[: max_len - 3] + "..."
    return s

def diff_locals(prev: Dict[str, Any], curr: Dict[str, Any]) -> Tuple[Dict, Dict, list]:
    added, updated, removed = {}, {}, []
    for k, v in curr.items():
        if k.startswith("__"):
            continue
        if k not in prev:
            added[k] = v
        elif prev[k] != v:
            updated[k] = (prev[k], v)
    for k in prev:
        if k.startswith("__"):
            continue
        if k not in curr:
            removed.append(k)
    return added, updated, removed
