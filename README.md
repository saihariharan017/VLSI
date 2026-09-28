# VLSI Assistant — Flask + Gemini 3.1 Flash-Lite

A production-oriented, domain-specific VLSI/EDA chatbot with **no login or registration**. It uses Flask, the Google `google-genai` SDK, Gemini `gemini-3.1-flash-lite`, server-side Flask sessions for temporary chat history, and Gunicorn for Render.

## What is included

- `app.py` — Flask routes, session isolation, domain guard, Gemini integration, security headers and error handling.
- `config.py` — title, domain, system prompt, behavior, welcome text, theme, limits and `PORT` configuration.
- `templates/index.html` — fully custom VLSI UI with responsive CSS and vanilla JavaScript.
- `.env.example` — environment variable template. **Never commit your real `.env`.**
- `requirements.txt` — Flask, Gemini SDK, dotenv and Gunicorn.
- `README.md` — beginner-friendly setup and Render instructions.

## 1. Get a Gemini API key

Create a Gemini API key using Google's Gemini API tooling. Keep the key private.

## 2. Local setup (Windows)

Open the project folder in VS Code, then open the terminal in that folder.

### Create a virtual environment

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation, you can still install/run with your Python interpreter, or use Command Prompt and run:

```bat
.venv\Scripts\activate.bat
```

### Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### Create `.env`

Copy `.env.example` to a new file named `.env`.

Put your real key into:

```env
GEMINI_API_KEY=your_real_key_here
FLASK_SECRET_KEY=your_long_random_secret_here
```

For local HTTP, keep:

```env
COOKIE_SECURE=false
```

### Start the app

```powershell
python app.py
```

Open:

`http://127.0.0.1:10000`

You can also run it the same way Render does:

```powershell
gunicorn app:app
```

On Windows, Gunicorn itself is not supported as a normal native Windows server, so use `python app.py` for local Windows testing. Render/Linux uses Gunicorn.

## 3. How the chatbot stays domain-specific

There are two layers:

1. A server-side keyword guard rejects clearly unrelated first questions before spending a Gemini request.
2. The Gemini system instruction strictly defines the VLSI/EDA scope and tells the model to politely reject unrelated questions.

Follow-up questions are allowed when the current temporary session already contains VLSI context.

## 4. Temporary session isolation

There is no account system and no shared conversation database.

Each browser session receives a random session namespace. The Flask-Session filesystem backend stores the bounded temporary history server-side; the browser receives only a signed session identifier. The API never accepts a client-supplied user ID or conversation ID, and `/api/history` reads only the current Flask session.

`Clear chat` calls `/api/clear`, clears the session state, and rotates the namespace.

The default backend in this project is a temporary server-side filesystem session, not a permanent database. On Render this filesystem is ephemeral, so conversations are intentionally temporary. If you later run multiple Render instances or need durable sessions, configure a shared Redis-backed Flask-Session store.

## 5. Render deployment

1. Push this project to a GitHub repository.
2. In Render, create **New → Web Service** and connect the repository.
3. Use:
   - **Language:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
4. Add environment variables in Render:
   - `GEMINI_API_KEY` = your real Gemini API key
   - `FLASK_SECRET_KEY` = a long random secret
   - `COOKIE_SECURE` = `true`
   - `GEMINI_MODEL` = `gemini-3.1-flash-lite`
5. Render supplies `PORT` automatically. The Flask app reads `PORT` from the environment, so you do **not** need to hard-code a Render port.
6. Deploy.

For the Render service, do not upload or commit `.env`. Put secrets in Render's Environment settings.

## 6. Customizing the chatbot

Open `config.py`. You can change:

- `TITLE`
- `DOMAIN`
- `TAGLINE`
- `MODEL_NAME`
- `PORT`
- `DOMAIN_DESCRIPTION`
- `DOMAIN_KEYWORDS`
- `SYSTEM_PROMPT`
- `WELCOME_MESSAGE`
- `UI` theme values
- message/history/rate limits

The Gemini API key is intentionally **not** configurable through frontend JavaScript or HTML.

## 7. Main routes

- `GET /` — chatbot UI
- `GET /health` — lightweight health check
- `GET /api/history` — current session's temporary messages
- `POST /api/chat` — send a message to Gemini
- `POST /api/clear` — clear and rotate the current session

## 8. Troubleshooting

### “Gemini is not configured yet”
Check that `.env` exists locally and contains `GEMINI_API_KEY=...`, then restart the Flask process.

### “Invalid API key” / Gemini 401 or 403
Create/check the Gemini API key and ensure the Gemini API is available for that key/project.

### Render starts but the page is unavailable
Check the Render logs and confirm the start command is exactly:

```text
gunicorn app:app
```

The app binds to `0.0.0.0` for direct local execution and reads Render's `PORT` environment variable.

### PowerShell says `pip` is not recognized
Use:

```powershell
python -m pip install -r requirements.txt
```

## Security notes

- No API key is rendered into HTML or JavaScript.
- Cookies are HTTP-only and SameSite=Lax.
- `COOKIE_SECURE=true` should be used on HTTPS production deployments.
- Response security headers include CSP, X-Frame-Options, Referrer-Policy and Permissions-Policy.
- Inputs have length limits.
- Session history is bounded.
- Basic per-session rate limiting is included.
- Errors shown to the browser do not expose exception details.
- The server does not log user prompts or Gemini responses.
