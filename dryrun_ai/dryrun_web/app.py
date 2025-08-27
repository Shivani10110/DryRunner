# app.py
import os
from flask import Flask, render_template, request, redirect, url_for
from dotenv import load_dotenv
from runner import run_in_subprocess
from llm import LLM
import json

load_dotenv()
app = Flask(__name__, static_folder="static", template_folder="templates")

@app.route("/", methods=["GET", "POST"])
def index():
    output_html = None
    summary = {}
    explain_mode = request.form.get("explain_mode", "only_changes")  # form control
    explain_all = (explain_mode == "all")
    if request.method == "POST":
        code = request.form.get("code", "")
        stdin = request.form.get("input_data", "")
        # runner returns events + stdout/stderr
        result = run_in_subprocess(code, input_text=stdin, max_steps=50000, hard_timeout_s=8)
        events = result.get("events", [])
        stdout = result.get("stdout", "")
        stderr = result.get("stderr", "")
        tle = result.get("tle")
        segfault = result.get("segfault")
        # LLM init
        llm = None
        try:
            llm = LLM()
        except Exception as e:
            llm = None
        enriched = []
        for evt in events:
            explanation = None
            # decide when to call LLM (to save tokens)
            call_llm = False
            if llm:
                if explain_all:
                    call_llm = True
                else:
                    # only when variable changed or exception or call/return
                    if evt.get("type") in ("exception", "call", "return"):
                        call_llm = True
                    elif evt.get("type") == "line" and (evt.get("added") or evt.get("updated") or evt.get("removed")):
                        call_llm = True
            if call_llm and llm:
                locals_str = "{ " + ", ".join(f"{k}={v}" for k, v in evt.get("locals", {}).items()) + " }"
                explanation = llm.explain(
                    code_line=evt.get("code", ""),
                    locals_str=locals_str,
                    added=evt.get("added", {}),
                    updated=evt.get("updated", {}),
                    removed=evt.get("removed", []),
                    event=evt.get("type", "line"),
                    error=evt.get("error"),
                    depth=int(evt.get("depth", 0)),
                )
            enriched.append({"evt": evt, "explanation": explanation})
        # build summary to pass to template
        summary = {
            "stdout": stdout,
            "stderr": stderr,
            "tle": tle,
            "segfault": segfault,
            "exitcode": result.get("exitcode"),
            "events_count": len(events),
        }
        return render_template("index.html", code=code, input_data=stdin, enriched=enriched, summary=summary, explain_mode=explain_mode)
    # GET
    return render_template("index.html", code="", input_data="", enriched=None, summary=None, explain_mode="only_changes")

if __name__ == "__main__":
    # dev server
    app.run(host="0.0.0.0", port=5000, debug=True)
