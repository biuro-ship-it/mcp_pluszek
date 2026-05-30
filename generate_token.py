#!/usr/bin/env python3
"""
generate_token.py — Generator tokenu serwisowego Firebase dla CRM Pluszek

Używa serviceAccountKey.json z backendu CRM do wygenerowania tokenu JWT,
który możesz wkleić jako CRM_BEARER_TOKEN w pliku .env.

Wymagania:
    pip install firebase-admin

Użycie:
    python generate_token.py
"""

import os
import sys

# ─── Ścieżka do klucza serwisowego ──────────────────────────────────────────

SERVICE_ACCOUNT_PATH = os.path.join(
    os.path.dirname(__file__),
    r"..\..\app_crm_pluszek\CRM-Pluszek\backend\serviceAccountKey.json",
)

# Możesz też podać ścieżkę bezpośrednio:
# SERVICE_ACCOUNT_PATH = r"D:\DEV\APLIKACJE\app_crm_pluszek\CRM-Pluszek\backend\serviceAccountKey.json"

# ─── UID użytkownika serwisowego ─────────────────────────────────────────────
# Podaj UID istniejącego użytkownika Firebase z uprawnieniami do CRM.
# Możesz sprawdzić w Firebase Console → Authentication → Users.

SERVICE_USER_UID = "SERVICE_ACCOUNT_UID_TUTAJ"

# ─── Generowanie tokenu ──────────────────────────────────────────────────────


def main() -> None:
    try:
        import firebase_admin
        from firebase_admin import auth, credentials
    except ImportError:
        print("Błąd: brak pakietu firebase-admin.")
        print("Zainstaluj go: pip install firebase-admin")
        sys.exit(1)

    if not os.path.isfile(SERVICE_ACCOUNT_PATH):
        print(f"Błąd: nie znaleziono pliku klucza serwisowego:")
        print(f"  {os.path.abspath(SERVICE_ACCOUNT_PATH)}")
        print("Sprawdź ścieżkę SERVICE_ACCOUNT_PATH w tym skrypcie.")
        sys.exit(1)

    if SERVICE_USER_UID == "SERVICE_ACCOUNT_UID_TUTAJ":
        print("Błąd: uzupełnij zmienną SERVICE_USER_UID w tym skrypcie.")
        print("Znajdziesz UID w Firebase Console → Authentication → Users.")
        sys.exit(1)

    # Inicjalizacja Firebase Admin SDK
    cred = credentials.Certificate(SERVICE_ACCOUNT_PATH)
    if not firebase_admin._apps:
        firebase_admin.initialize_app(cred)

    # Generowanie custom tokenu (długoterminowy — wymaga wymiany na ID token)
    custom_token: bytes = auth.create_custom_token(SERVICE_USER_UID)
    token_str: str = custom_token.decode("utf-8") if isinstance(custom_token, bytes) else custom_token

    print("\n" + "=" * 60)
    print("Custom token Firebase (JWT) wygenerowany pomyślnie!")
    print("=" * 60)
    print("\nWklej do pliku .env jako CRM_BEARER_TOKEN:\n")
    print(f"CRM_BEARER_TOKEN={token_str}")
    print("\n" + "=" * 60)
    print("\nUWAGA: Custom token Firebase ma ważność ~1h i musi być wymieniony")
    print("na ID token przez Firebase REST API lub SDK po stronie klienta.")
    print("Jeśli Twój backend akceptuje custom token bezpośrednio — gotowe.")
    print("Jeśli wymaga ID token — skontaktuj się z autorem backendu CRM.")


if __name__ == "__main__":
    main()
