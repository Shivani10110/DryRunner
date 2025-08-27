# llm.py
import os
from typing import Dict, Optional
from dotenv import load_dotenv
import openai

load_dotenv()
OPENAI_MODEL_DEFAULT = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

class LLM:
    def __init__(self, model: Optional[str] = None):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set. Put it in .env or environment.")
        openai.api_key = api_key
        self.model = model or OPENAI_MODEL_DEFAULT

    def explain(self,
                *,
                code_line: str,
                locals_str: str,
                added: Dict,
                updated: Dict,
                removed: list,
                event: str,
                error: Optional[str] = None,
                depth: int = 0) -> str:
        """
        Return one-sentence beginner-friendly explanation (call OpenAI).
        Keep prompt short to save tokens.
        """
        system = ("You are a friendly programming tutor. Explain the execution step in one short sentence "
                  "in simple language (Hinglish/English ok). If there's an error or TLE risk, mention it briefly.")
        added_keys = list(added.keys())
        updated_keys = list(updated.keys())
        user = (
            f"Event: {event}\nDepth: {depth}\nLine: {code_line}\n"
            f"Locals: {locals_str}\nAdded: {added_keys}; Updated: {updated_keys}; Removed: {removed}\n"
            + (f"Error: {error}\n" if error else "")
            + "Explain briefly."
        )
        try:
            resp = openai.ChatCompletion.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=0.2,
                max_tokens=80,
            )
            # parse response
            if "choices" in resp and len(resp["choices"]) > 0:
                ch = resp["choices"][0]
                if "message" in ch and "content" in ch["message"]:
                    return ch["message"]["content"].strip()
                if "text" in ch:
                    return ch["text"].strip()
            return "(LLM: no response)"
        except Exception as e:
            return f"(LLM error: {e})"
