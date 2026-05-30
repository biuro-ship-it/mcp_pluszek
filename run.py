#!/usr/bin/env python3
"""
run.py — Launcher CRM Pluszek MCP Server z automatycznym odświeżaniem tokenu.

Uruchamia src/server.py i co 55 minut pobiera nowy token Firebase,
aktualizuje .env i restartuje serwer — bez żadnej ręcznej interwencji.

Użycie:
    python run.py
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
from dotenv import dotenv_values, load_dotenv

# ─── Konfiguracja ────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent
ENV_FILE = BASE_DIR / ".env"
SERVER_SCRIPT = BASE_DIR / "src" / "server.py"

FIREBASE_API_KEY = "AIzaSyBKgg3Qg0h0eqWP1vQCoJbXSvuCJrtyIG4"
FIREBASE_REFRESH_TOKEN_KEY = "FIREBASE_REFRESH_TOKEN"

# Co ile sekund odświeżać token (55 minut — token ważny 60 min)
REFRESH_INTERVAL = 55 * 60


# ─── Odświeżanie tokenu ──────────────────────────────────────────────────────


def get_refresh_token() -> str:
    """Czyta refresh token z .env."""
    env = dotenv_values(ENV_FILE)
    token = env.get(FIREBASE_REFRESH_TOKEN_KEY, "").strip()
    if not token:
        raise RuntimeError(
            f"Brak {FIREBASE_REFRESH_TOKEN_KEY} w pliku .env.\n"
            "Dodaj linię: FIREBASE_REFRESH_TOKEN=<twój_refresh_token>"
        )
    return token


def fetch_new_id_token(refresh_token: str) -> str:
    """Pobiera nowy ID token z Firebase REST API używając refresh tokenu."""
    url = f"https://securetoken.googleapis.com/v1/token?key={FIREBASE_API_KEY}"
    resp = httpx.post(
        url,
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()
    id_token = data.get("id_token")
    if not id_token:
        raise RuntimeError(f"Brak id_token w odpowiedzi Firebase: {data}")
    return id_token


def update_env_token(new_token: str) -> None:
    """Aktualizuje CRM_BEARER_TOKEN w pliku .env."""
    content = ENV_FILE.read_text(encoding="utf-8")
    content = re.sub(
        r"^CRM_BEARER_TOKEN=.*$",
        f"CRM_BEARER_TOKEN={new_token}",
        content,
        flags=re.MULTILINE,
    )
    ENV_FILE.write_text(content, encoding="utf-8")


def refresh_token_cycle() -> bool:
    """Pobiera nowy token i zapisuje do .env. Zwraca True przy sukcesie."""
    try:
        print("[token] Pobieranie nowego tokenu Firebase...", flush=True)
        refresh_token = get_refresh_token()
        new_token = fetch_new_id_token(refresh_token)
        update_env_token(new_token)
        print("[token] Token odświeżony pomyślnie.", flush=True)
        return True
    except httpx.HTTPStatusError as e:
        print(f"[token] Błąd HTTP {e.response.status_code}: {e.response.text[:200]}", flush=True)
        return False
    except Exception as e:
        print(f"[token] Błąd odświeżania tokenu: {e}", flush=True)
        return False


# ─── Zarządzanie procesem serwera ────────────────────────────────────────────


def start_server() -> subprocess.Popen:
    """Uruchamia src/server.py jako subprocess."""
    print("[serwer] Uruchamianie CRM Pluszek MCP Server...", flush=True)
    proc = subprocess.Popen(
        [sys.executable, str(SERVER_SCRIPT)],
        cwd=str(BASE_DIR),
    )
    time.sleep(2)  # chwila na start uvicorn
    if proc.poll() is not None:
        raise RuntimeError(f"Serwer zakończył się natychmiast (kod: {proc.returncode}). Sprawdź .env.")
    print(f"[serwer] Uruchomiony (PID: {proc.pid}) → http://localhost:8000/mcp", flush=True)
    return proc


def stop_server(proc: subprocess.Popen) -> None:
    """Zatrzymuje subprocess serwera."""
    if proc.poll() is None:
        print(f"[serwer] Zatrzymywanie (PID: {proc.pid})...", flush=True)
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
        print("[serwer] Zatrzymany.", flush=True)


# ─── Pętla główna ─────────────────────────────────────────────────────────────


def main() -> None:
    # Weryfikacja pliku .env
    if not ENV_FILE.exists():
        print(f"Błąd: brak pliku {ENV_FILE}. Skopiuj .env.example jako .env i uzupełnij.")
        sys.exit(1)

    # Sprawdź czy jest refresh token
    env = dotenv_values(ENV_FILE)
    if not env.get(FIREBASE_REFRESH_TOKEN_KEY):
        print(f"Błąd: brak {FIREBASE_REFRESH_TOKEN_KEY} w .env.")
        print(f"Dodaj linię: FIREBASE_REFRESH_TOKEN=<twój_refresh_token>")
        sys.exit(1)

    # Pierwsze odświeżenie tokenu przed startem
    print("[start] Odświeżam token przed uruchomieniem serwera...", flush=True)
    refresh_token_cycle()

    proc = start_server()
    last_refresh = time.time()

    try:
        while True:
            time.sleep(10)

            # Sprawdź czy serwer żyje
            if proc.poll() is not None:
                print(f"[serwer] Proces zakończył się (kod: {proc.returncode}). Restartuję...", flush=True)
                time.sleep(3)
                proc = start_server()
                last_refresh = time.time()
                continue

            # Odśwież token co REFRESH_INTERVAL sekund
            if time.time() - last_refresh >= REFRESH_INTERVAL:
                success = refresh_token_cycle()
                if success:
                    print("[serwer] Restartuję serwer z nowym tokenem...", flush=True)
                    stop_server(proc)
                    time.sleep(1)
                    proc = start_server()
                last_refresh = time.time()

    except KeyboardInterrupt:
        print("\n[stop] Ctrl+C — zatrzymywanie...", flush=True)
        stop_server(proc)
        print("[stop] Gotowe.", flush=True)


if __name__ == "__main__":
    main()
