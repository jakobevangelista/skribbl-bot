"""Local guess service.

The extension posts the canvas and the hint. This process asks a local vision
model for candidate words, then keeps only the ones that fit the hint.
A follow-up request can send the previous raw list and no image, which
refilters when Skribbl reveals a letter without another vision pass.

Environment:
  MODEL_URL   default http://127.0.0.1:11434/api/chat
  MODEL_NAME  default qwen3.5:4b
  PORT        default 8765
  WORDS_FILE  default ../words/en.txt next to this file, optional
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from parse import parse_candidates
from pattern import pattern_text, slots_from_hints
from rank import TIGHT_LIMIT, matching_words, rank

ROOT = Path(__file__).resolve().parent
DEFAULT_WORDS = ROOT.parent / "words" / "en.txt"
MAX_IMAGE_CHARS = 6_000_000


def load_dictionary(path: Path) -> list[str]:
    if not path.is_file():
        return []
    words: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip().lower()
        if line:
            words.append(line)
    return words


def build_prompt(pattern: str, rejected: list[str] | None = None) -> str:
    # The board is applied in code. This model cannot spell to a pattern, so the
    # picture is only asked for what the sketch depicts.
    del pattern
    reject_line = ""
    if rejected:
        reject_line = " Do not repeat: " + ", ".join(rejected) + "."
    return (
        "This is a bad sketch from skribbl.io. Someone is trying to draw a thing. "
        "Name the objects, animals, actions, or characters it might be. "
        "8 guesses, most likely first. One per line. Lowercase. "
        "Short nouns or phrases. No sentences."
        f"{reject_line}"
    )


def _fits_pattern(word: str, pattern: str) -> bool:
    """Length and revealed letters, using the same pattern string sent to the model."""
    if pattern == "hidden":
        return bool(word.strip())
    text = word.strip().lower()
    if len(text) != len(pattern):
        return False
    for char, slot in zip(text, pattern):
        if slot == "_":
            if not char.isalnum():
                return False
        elif slot == " ":
            if char not in (" ", "-"):
                return False
        elif char != slot:
            return False
    return True


def retry_prompt(pattern: str, text: str) -> str | None:
    """Ask again when the model ignored the length or the revealed letters."""
    if pattern == "hidden":
        return None
    words = parse_candidates(text)
    if any(_fits_pattern(word, pattern) for word in words):
        return None
    return build_prompt(pattern, words[:8])


def ask_model(image_b64: str, pattern: str) -> str:
    return _complete(image_b64, build_prompt(pattern))


def _complete(image_b64: str, prompt: str) -> str:
    url = os.environ.get("MODEL_URL", "http://127.0.0.1:11434/api/chat")
    model = os.environ.get("MODEL_NAME", "qwen3.5:4b")
    if url.rstrip("/").endswith("/api/chat"):
        body = {
            "model": model,
            "stream": False,
            "think": False,
            "options": {"temperature": 0.2, "num_predict": 80},
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [image_b64],
                }
            ],
        }
    else:
        body = {
            "model": model,
            "max_tokens": 80,
            "temperature": 0.2,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{image_b64}"},
                        },
                    ],
                }
            ],
        }
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise RuntimeError(f"vision model is unreachable at {url}: {exc}") from exc
    return _message_text(payload)


def _message_text(payload: dict) -> str:
    message = payload.get("message") or {}
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    choices = payload.get("choices") or []
    if choices:
        content = (choices[0].get("message") or {}).get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "\n".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )
    raise RuntimeError("vision model returned no text")


def handle_payload(data: dict, ask, dictionary: list[str]) -> dict:
    hints = data.get("hints") or []
    if not isinstance(hints, list) or not all(isinstance(hint, str) for hint in hints):
        raise ValueError("hints must be a list of strings")
    word_length = str(data.get("word_length") or "")
    slots = slots_from_hints(hints, word_length)
    pattern = pattern_text(slots)
    rejects = data.get("rejects") or []
    if not isinstance(rejects, list):
        raise ValueError("rejects must be a list")
    image = data.get("image") or ""
    rejects_text = [str(word) for word in rejects]
    # A specific board already names every legal word. Looking at a bad drawing
    # only slows that down and pulls the guess toward the wrong shape.
    letter_only = matching_words(slots, dictionary, rejects_text)
    tight = slots is not None and 0 < len(letter_only) <= TIGHT_LIMIT
    raw = data.get("raw")
    if image and not isinstance(image, str):
        raise ValueError("image must be base64 text")
    if isinstance(image, str) and image.startswith("data:"):
        image = image.split(",", 1)[-1]
    if image and len(image) > MAX_IMAGE_CHARS:
        raise ValueError("image is too large")
    model_ms = None
    error = None
    if image and not tight:
        started = time.perf_counter()
        try:
            text = ask(image, pattern)
            raw = parse_candidates(text)
        except Exception as exc:
            error = str(exc)
            raw = raw if isinstance(raw, list) else []
        model_ms = int((time.perf_counter() - started) * 1000)
    elif tight:
        raw = raw if isinstance(raw, list) else []
    elif not isinstance(raw, list):
        raise ValueError("send an image, or raw candidates to refilter")
    else:
        raw = [str(word) for word in raw]
    guesses, close, _extra = rank(raw, slots, dictionary, rejects_text)
    return {
        "pattern": pattern,
        "guesses": guesses,
        "close": close[:8],
        "dictionary": [],
        "raw": raw,
        "model_ms": model_ms,
        "error": error,
    }


class Handler(BaseHTTPRequestHandler):
    dictionary: list[str] = []

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("%s - %s\n" % (self.address_string(), fmt % args))

    def _send(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.send_header("access-control-allow-origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("access-control-allow-origin", "*")
        self.send_header("access-control-allow-methods", "GET, POST, OPTIONS")
        self.send_header("access-control-allow-headers", "content-type")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.split("?", 1)[0] != "/health":
            self._send(404, {"error": "not found"})
            return
        self._send(
            200,
            {
                "ok": True,
                "model": os.environ.get("MODEL_NAME", "qwen3.5:4b"),
                "words": len(self.dictionary),
            },
        )

    def do_POST(self) -> None:
        if self.path.split("?", 1)[0] != "/guess":
            self._send(404, {"error": "not found"})
            return
        length = int(self.headers.get("content-length") or "0")
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8") or "{}")
            if not isinstance(data, dict):
                raise ValueError("body must be an object")
            payload = handle_payload(data, ask_model, self.dictionary)
        except ValueError as exc:
            self._send(400, {"error": str(exc)})
            return
        except json.JSONDecodeError:
            self._send(400, {"error": "body must be json"})
            return
        self._send(200, payload)


def serve(port: int, words_path: Path) -> None:
    Handler.dictionary = load_dictionary(words_path)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(
        f"guess server on http://127.0.0.1:{port}  "
        f"model={os.environ.get('MODEL_NAME', 'qwen3.5:4b')}  "
        f"words={len(Handler.dictionary)}",
        flush=True,
    )
    server.serve_forever()


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description="Suggest Skribbl answers from a drawing")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--words", type=Path, default=Path(os.environ.get("WORDS_FILE", DEFAULT_WORDS)))
    parser.add_argument("--image", type=Path, help="Run one guess from a PNG and exit")
    parser.add_argument("--hints", nargs="*", default=[])
    parser.add_argument("--word-length", default="")
    args = parser.parse_args(argv)
    if args.image:
        image = base64.b64encode(args.image.read_bytes()).decode("ascii")
        payload = handle_payload(
            {"image": image, "hints": args.hints, "word_length": args.word_length},
            ask_model,
            load_dictionary(args.words),
        )
        json.dump(payload, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return
    serve(args.port, args.words)


if __name__ == "__main__":
    main(sys.argv[1:])
