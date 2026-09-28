"""Small dependency/runtime smoke test used before deployment."""
import os
import py_compile
from pathlib import Path

os.environ.setdefault("FLASK_SECRET_KEY", "smoke-test-secret")
os.environ.setdefault("COOKIE_SECURE", "false")

for path in [Path("app.py"), Path("config.py")]:
    py_compile.compile(str(path), doraise=True)

from app import app

with app.test_client() as client:
    assert client.get("/").status_code == 200
    assert client.get("/health").status_code == 200
    assert client.post("/api/chat", json={"message": ""}).status_code == 400
    assert client.post("/api/chat", json={"message": "hello"}).status_code == 200
    assert client.post("/api/chat", json={"message": "Tell me a football score"}).status_code == 200
    assert client.post("/api/clear").status_code == 200

print("Smoke test passed: syntax, routes, template, sessions, domain guard, greeting, and clear-chat.")
