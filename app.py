import logging
import os
import secrets
import time
from functools import wraps

from flask import Flask, jsonify, render_template, request, session
from flask_session import Session
from google import genai
from google.genai import types

import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vlsi_assistant")

app = Flask(__name__)
secret_key = config.SECRET_KEY or secrets.token_hex(32)
app.secret_key = secret_key
app.config.update(
    SESSION_TYPE="filesystem",
    SESSION_FILE_DIR=os.getenv("SESSION_FILE_DIR", "/tmp/vlsi_assistant_sessions"),
    SESSION_PERMANENT=False,
    SESSION_USE_SIGNER=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=config.COOKIE_SECURE,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_NAME="vlsi_assistant_session",
    MAX_CONTENT_LENGTH=32 * 1024,
)
Session(app)

# The key is read only on the server. It is never passed to templates or JSON responses.
gemini_client = genai.Client(api_key=config.GEMINI_API_KEY) if config.GEMINI_API_KEY else None

ALLOWED_GREETING_WORDS = {"hi", "hello", "hey", "hii", "helo", "good morning", "good afternoon", "good evening"}


def normalize(text: str) -> str:
    return " ".join(text.lower().strip().split())


def is_greeting(text: str) -> bool:
    normalized = normalize(text).strip(".!?,")
    return normalized in ALLOWED_GREETING_WORDS


def looks_domain_relevant(text: str) -> bool:
    normalized = normalize(text)
    return any(keyword in normalized for keyword in config.DOMAIN_KEYWORDS)


def domain_rejection() -> str:
    return (
        f"I’m focused only on {config.DOMAIN}. Please ask me about topics such as RTL, CMOS, "
        "synthesis, timing, physical design, PPA, low-power VLSI, ASIC/FPGA, or EDA flows."
    )


def get_history():
    history = session.get("chat_history")
    if not isinstance(history, list):
        history = []
        session["chat_history"] = history
    return history


def enforce_session_namespace():
    # A per-session random nonce makes the isolation boundary explicit and gives us a stable
    # namespace identifier without collecting an account identity or device fingerprint.
    if "session_namespace" not in session:
        session["session_namespace"] = secrets.token_urlsafe(18)
        session.modified = True


def rate_limited() -> bool:
    now = time.time()
    window = session.get("rate_window", {"started": now, "count": 0})
    if not isinstance(window, dict):
        window = {"started": now, "count": 0}
    if now - float(window.get("started", now)) >= 60:
        window = {"started": now, "count": 0}
    if int(window.get("count", 0)) >= config.RATE_LIMIT_PER_MINUTE:
        session["rate_window"] = window
        session.modified = True
        return True
    window["count"] = int(window.get("count", 0)) + 1
    session["rate_window"] = window
    session.modified = True
    return False


def no_cache(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        response = view(*args, **kwargs)
        response.headers["Cache-Control"] = "no-store, max-age=0"
        response.headers["Pragma"] = "no-cache"
        return response

    return wrapped


@app.before_request
def prepare_session():
    enforce_session_namespace()


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self' data:; font-src 'self' data:; frame-ancestors 'none'"
    )
    return response


@app.get("/")
@no_cache
def index():
    return render_template("index.html", ui=config.UI)


@app.get("/health")
@no_cache
def health():
    return jsonify({"status": "ok", "configured": bool(config.GEMINI_API_KEY), "model": config.MODEL_NAME})


@app.get("/api/history")
@no_cache
def history():
    # Only this signed session's own history is returned. There is no global conversation store.
    return jsonify({"messages": get_history()})


@app.post("/api/chat")
@no_cache
def chat():
    if not request.is_json:
        return jsonify({"error": "Request must use JSON."}), 415

    payload = request.get_json(silent=True) or {}
    message = payload.get("message")
    if not isinstance(message, str):
        return jsonify({"error": "Message must be text."}), 400

    message = message.strip()
    if not message:
        return jsonify({"error": "Please enter a question."}), 400
    if len(message) > config.MAX_MESSAGE_CHARS:
        return jsonify({"error": f"Please keep your message under {config.MAX_MESSAGE_CHARS} characters."}), 413
    if rate_limited():
        return jsonify({"error": "Too many requests in a short period. Please wait a moment and try again."}), 429

    history = get_history()

    # Deterministic first-pass domain guard reduces unnecessary model calls for clearly unrelated prompts.
    # Follow-ups are allowed when this session already has VLSI context.
    if not is_greeting(message) and not looks_domain_relevant(message) and not history:
        answer = domain_rejection()
        history.extend([{"role": "user", "text": message}, {"role": "assistant", "text": answer}])
        session["chat_history"] = history[-config.MAX_HISTORY_MESSAGES :]
        session.modified = True
        return jsonify({"answer": answer})

    if is_greeting(message):
        answer = config.WELCOME_MESSAGE
        history.extend([{"role": "user", "text": message}, {"role": "assistant", "text": answer}])
        session["chat_history"] = history[-config.MAX_HISTORY_MESSAGES :]
        session.modified = True
        return jsonify({"answer": answer})

    if gemini_client is None:
        logger.error("GEMINI_API_KEY is not configured")
        return jsonify({"error": "Gemini is not configured yet. Add GEMINI_API_KEY to your .env file."}), 503

    # Build a bounded conversation for this session only.
    contents = []
    for item in history[-config.MAX_HISTORY_MESSAGES :]:
        role = "model" if item.get("role") == "assistant" else "user"
        text = item.get("text", "")
        if text:
            contents.append(types.Content(role=role, parts=[types.Part.from_text(text=text)]))
    contents.append(types.Content(role="user", parts=[types.Part.from_text(text=message)]))

    try:
        response = gemini_client.models.generate_content(
            model=config.MODEL_NAME,
            contents=contents,
            config=types.GenerateContentConfig(
                system_instruction=config.SYSTEM_PROMPT,
                max_output_tokens=1200,
                thinking_config=types.ThinkingConfig(thinking_level="low"),
            ),
        )
        answer = (response.text or "").strip()
        if not answer:
            raise RuntimeError("Gemini returned an empty response")
    except Exception:
        logger.exception("Gemini request failed")
        return jsonify({"error": "I couldn't reach Gemini right now. Please try again in a moment."}), 502

    history.extend([{"role": "user", "text": message}, {"role": "assistant", "text": answer}])
    session["chat_history"] = history[-config.MAX_HISTORY_MESSAGES :]
    session.modified = True
    return jsonify({"answer": answer})


@app.post("/api/clear")
@no_cache
def clear_chat():
    # Rotate the session namespace and remove all chat/rate-limit state.
    session.clear()
    session["session_namespace"] = secrets.token_urlsafe(18)
    session.modified = True
    return jsonify({"ok": True})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=config.PORT, debug=False)
