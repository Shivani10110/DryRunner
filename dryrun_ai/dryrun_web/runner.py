# runner.py
import sys
import io
import time
import signal
import multiprocessing as mp
from types import FrameType
from typing import Dict, Any
from utils import diff_locals, safe_repr

def _compute_depth(frame: FrameType, filename: str) -> int:
    d, f = 0, frame
    while f:
        if getattr(f.f_code, "co_filename", "") == filename:
            d += 1
        f = f.f_back
    return max(0, d - 1)

def _runner(code: str, filename: str, q: mp.Queue, max_steps: int, hard_timeout_s: int, stdin_text: str):
    start = time.time()
    step_count = 0
    prev_locals: Dict[int, Dict[str, Any]] = {}

    # redirect IO
    sys.stdin = io.StringIO(stdin_text or "")
    out_buf, err_buf = io.StringIO(), io.StringIO()
    sys.stdout = out_buf
    sys.stderr = err_buf

    lines = [""] + code.splitlines()

    def tracer(frame: FrameType, event: str, arg):
        nonlocal step_count
        # only trace our virtual file
        if frame.f_code.co_filename != filename:
            return tracer

        depth = _compute_depth(frame, filename)
        lineno = frame.f_lineno
        code_line = lines[lineno].strip() if 0 < lineno < len(lines) else ""

        step_count += 1
        # TLE/time guard
        if step_count > max_steps or (time.time() - start) > hard_timeout_s:
            q.put({"type": "tle", "lineno": lineno, "code": code_line, "depth": depth,
                   "reason": f"Exceeded limits (steps>{max_steps} or time>{hard_timeout_s}s)"})
            return None

        if event == "call":
            q.put({"type": "call", "lineno": lineno, "code": code_line, "func": frame.f_code.co_name, "depth": depth})
            prev_locals[id(frame)] = dict(frame.f_locals)
            return tracer

        if event == "line":
            fid = id(frame)
            before = prev_locals.get(fid, {})
            now = dict(frame.f_locals)
            added, updated, removed = diff_locals(before, now)
            prev_locals[fid] = dict(now)
            q.put({
                "type": "line", "lineno": lineno, "code": code_line, "depth": depth,
                "locals": {k: safe_repr(v) for k, v in now.items() if not k.startswith("__")},
                "added": {k: safe_repr(v) for k, v in added.items()},
                "updated": {k: (safe_repr(a), safe_repr(b)) for k, (a, b) in updated.items()},
                "removed": removed,
            })
            return tracer

        if event == "return":
            q.put({"type": "return", "lineno": lineno, "code": code_line, "depth": depth,
                   "func": frame.f_code.co_name, "retval": safe_repr(arg)})
            return tracer

        if event == "exception":
            etype, evalue, tb = arg
            q.put({
                "type": "exception", "lineno": lineno, "code": code_line, "depth": depth,
                "error": f"{etype.__name__}: {evalue}",
            })
            return tracer

        return tracer

    g = {"__name__": "__main__", "__builtins__": __builtins__}
    sys.settrace(tracer)
    try:
        exec(compile(code, filename, "exec"), g, g)
    finally:
        sys.settrace(None)
        q.put({"type": "stdout", "data": out_buf.getvalue()})
        q.put({"type": "stderr", "data": err_buf.getvalue()})
        q.put({"type": "done", "steps": step_count})

def run_in_subprocess(code: str, input_text: str = "", max_steps: int = 50000, hard_timeout_s: int = 8):
    ctx = mp.get_context("spawn")
    q: mp.Queue = ctx.Queue()
    filename = "<user-code>"

    proc = ctx.Process(target=_runner, args=(code, filename, q, max_steps, hard_timeout_s, input_text))
    proc.start()

    events = []
    segfault = False
    tle_seen = False
    stdout_data, stderr_data = "", ""

    while True:
        if not proc.is_alive() and q.empty():
            break
        try:
            evt = q.get(timeout=0.1)
            if evt.get("type") == "stdout":
                stdout_data = evt.get("data", "")
            elif evt.get("type") == "stderr":
                stderr_data = evt.get("data", "")
            else:
                events.append(evt)
                if evt.get("type") == "tle":
                    tle_seen = True
        except Exception:
            pass

    proc.join(timeout=0.1)
    if proc.exitcode is not None and proc.exitcode < 0:
        segfault = (-proc.exitcode == signal.SIGSEGV)

    return {
        "events": events,
        "segfault": segfault,
        "exitcode": proc.exitcode,
        "tle": tle_seen,
        "stdout": stdout_data,
        "stderr": stderr_data,
    }
