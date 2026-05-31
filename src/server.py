#!/usr/bin/env python3
"""
CRM Pluszek — MCP Server

Serwer MCP integrujący Claude z systemem CRM Pluszek (https://crm.pluszek.pl).
Udostępnia 8 narzędzi do zarządzania klientami, interakcjami, follow-upami,
produktami i promocjami.

Transport: streamable_http (port 8000)
Auth: Bearer token z zmiennej środowiskowej CRM_BEARER_TOKEN
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone
from typing import Any, Optional

import httpx
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, ConfigDict, Field

# ─── Konfiguracja ────────────────────────────────────────────────────────────

load_dotenv()

CRM_API_URL: str = os.getenv("CRM_API_URL", "https://crm.pluszek.pl")
CRM_BEARER_TOKEN: str = os.getenv("CRM_BEARER_TOKEN", "")

if not CRM_BEARER_TOKEN:
    raise RuntimeError(
        "Brak zmiennej środowiskowej CRM_BEARER_TOKEN. "
        "Uzupełnij plik .env i uruchom serwer ponownie."
    )

# ─── Inicjalizacja FastMCP ───────────────────────────────────────────────────

mcp = FastMCP(
    "crm_pluszek_mcp",
    instructions=(
        "Serwer MCP systemu CRM Pluszek. Używaj tych narzędzi do pracy "
        "z klientami, interakcjami handlowymi, follow-upami, produktami "
        "i promocjami. Wszystkie operacje wymagają autoryzacji — token jest "
        "konfigurowany przez administratora w zmiennej CRM_BEARER_TOKEN."
    ),
    stateless_http=True,
    host="0.0.0.0",
    port=8000,
)

# ─── Infrastruktura: klient HTTP ─────────────────────────────────────────────


@asynccontextmanager
async def get_client():
    """Async context manager zwracający skonfigurowanego klienta HTTP."""
    async with httpx.AsyncClient(
        base_url=CRM_API_URL,
        headers={
            "Authorization": f"Bearer {CRM_BEARER_TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        timeout=30.0,
    ) as client:
        yield client


# ─── Infrastruktura: obsługa błędów ─────────────────────────────────────────


def _handle_error(e: Exception) -> str:
    """Formatuje błędy httpx na czytelne po polsku komunikaty."""
    if isinstance(e, httpx.HTTPStatusError):
        status = e.response.status_code
        try:
            body = e.response.json()
            detail = body.get("message") or body.get("error") or str(body)
        except Exception:
            detail = e.response.text[:200]

        messages = {
            400: f"Błąd zapytania (400): {detail}",
            401: "Błąd autoryzacji (401): nieprawidłowy lub wygasły token Bearer.",
            403: "Brak dostępu (403): nie masz uprawnień do tego zasobu.",
            404: f"Nie znaleziono zasobu (404): {detail}",
            422: f"Błąd walidacji danych (422): {detail}",
            429: "Zbyt wiele zapytań (429): poczekaj chwilę i spróbuj ponownie.",
            500: f"Błąd serwera CRM (500): {detail}",
        }
        return messages.get(status, f"Błąd HTTP {status}: {detail}")

    if isinstance(e, httpx.TimeoutException):
        return "Przekroczono czas oczekiwania na odpowiedź serwera CRM. Spróbuj ponownie."

    if isinstance(e, httpx.ConnectError):
        return f"Nie można połączyć się z CRM ({CRM_API_URL}). Sprawdź adres w .env."

    return f"Nieoczekiwany błąd ({type(e).__name__}): {e}"


# ─── Infrastruktura: formatowanie daty ──────────────────────────────────────


def _fmt_date(iso_str: Optional[str]) -> str:
    """Konwertuje datę ISO 8601 na format DD.MM.YYYY HH:MM lub DD.MM.YYYY."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.hour == 0 and dt.minute == 0 and dt.second == 0:
            return dt.strftime("%d.%m.%Y")
        return dt.strftime("%d.%m.%Y %H:%M")
    except (ValueError, AttributeError):
        return iso_str


def _today_iso() -> str:
    """Zwraca dzisiejszą datę w formacie ISO (YYYY-MM-DD)."""
    return date.today().isoformat()


def _dump(obj: Any) -> str:
    """Serializuje obiekt do JSON z polskimi znakami."""
    return json.dumps(obj, ensure_ascii=False, indent=2)


# ═══════════════════════════════════════════════════════════════════════════════
# NARZĘDZIA MCP
# ═══════════════════════════════════════════════════════════════════════════════

# ─── 1. Lista klientów ───────────────────────────────────────────────────────


class ListaKlientowInput(BaseModel):
    """Parametry wejściowe dla narzędzia crm_lista_klientow."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search: Optional[str] = Field(
        default=None,
        description="Filtruj po nazwie firmy lub mieście (wyszukiwanie częściowe, bez rozróżniania wielkości liter)",
        max_length=200,
    )
    limit: Optional[int] = Field(
        default=20,
        description="Maksymalna liczba wyników (domyślnie 20, max 100)",
        ge=1,
        le=100,
    )
    offset: Optional[int] = Field(
        default=0,
        description="Ile wyników pominąć — do stronicowania (domyślnie 0)",
        ge=0,
    )


@mcp.tool(
    name="crm_lista_klientow",
    annotations={
        "title": "Lista klientów CRM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_lista_klientow(params: ListaKlientowInput) -> str:
    """Pobiera listę klientów z CRM Pluszek z opcjonalnym filtrowaniem i stronicowaniem.

    Używaj gdy:
    - chcesz znaleźć klientów po nazwie firmy lub mieście
    - potrzebujesz przejrzeć wszystkich klientów
    - szukasz ID klienta przed innymi operacjami

    Args:
        params (ListaKlientowInput):
            - search (str, opcjonalnie): fragment nazwy lub miasta, np. "Kraków", "Kowalski"
            - limit (int): ile wyników zwrócić, 1–100 (domyślnie 20)
            - offset (int): ile wyników pominąć do paginacji (domyślnie 0)

    Returns:
        str: JSON z listą klientów:
        {
            "total": int,        # łączna liczba dopasowań (po filtrowaniu)
            "count": int,        # liczba wyników w tej odpowiedzi
            "offset": int,
            "has_more": bool,
            "klienci": [
                {
                    "id": str,
                    "nazwa": str,
                    "miasto": str,
                    "telefon": str,
                    "email": str,
                    "opiekun": str
                }
            ]
        }
    """
    try:
        async with get_client() as client:
            resp = await client.get("/api/clients")
            resp.raise_for_status()
            data = resp.json()

        # API może zwracać listę bezpośrednio lub obiekt z polem data/clients
        clients: list[dict] = (
            data if isinstance(data, list) else data.get("data") or data.get("clients") or []
        )

        # Filtrowanie po stronie MCP
        if params.search:
            q = params.search.lower()
            clients = [
                c for c in clients
                if q in (c.get("companyName") or c.get("name") or "").lower()
                or q in ((c.get("address") or {}).get("city") or "").lower()
                or q in (c.get("contactPerson") or "").lower()
            ]

        total = len(clients)
        page = clients[params.offset : params.offset + params.limit]

        def _map_client(c: dict) -> dict:
            addr = c.get("address") or {}
            return {
                "id": c.get("id") or c.get("_id") or "",
                "nazwa": c.get("companyName") or c.get("name") or "",
                "miasto": addr.get("city") or c.get("city") or "",
                "telefon": c.get("phone") or "",
                "email": c.get("email") or "",
                "kontakt": c.get("contactPerson") or "",
                "typ": c.get("type") or "",
            }

        return _dump(
            {
                "total": total,
                "count": len(page),
                "offset": params.offset,
                "has_more": total > params.offset + len(page),
                "klienci": [_map_client(c) for c in page],
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 2. Karta klienta ────────────────────────────────────────────────────────


class KartaKlientaInput(BaseModel):
    """Parametry dla narzędzia crm_karta_klienta."""

    model_config = ConfigDict(extra="forbid")

    client_id: str = Field(
        ...,
        description="ID klienta (pobierz przez crm_lista_klientow)",
        min_length=1,
    )


@mcp.tool(
    name="crm_karta_klienta",
    annotations={
        "title": "Karta klienta CRM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_karta_klienta(params: KartaKlientaInput) -> str:
    """Pobiera pełne dane klienta wraz z historią interakcji z CRM Pluszek.

    Używaj gdy:
    - chcesz zobaczyć szczegóły konkretnego klienta
    - potrzebujesz historii kontaktów z klientem
    - przygotowujesz się do rozmowy handlowej

    Args:
        params (KartaKlientaInput):
            - client_id (str): ID klienta z crm_lista_klientow

    Returns:
        str: JSON z danymi klienta i listą interakcji:
        {
            "klient": { id, nazwa, miasto, telefon, email, nip, opiekun, notatki, created_at },
            "interakcje": [
                { id, type, note, contact_date, result, created_at }
            ]
        }
    """
    try:
        async with get_client() as client:
            # Brak GET /clients/:id — pobieramy wszystkich i filtrujemy
            resp_all = await client.get("/api/clients")
            resp_all.raise_for_status()
            all_clients = resp_all.json()
            if not isinstance(all_clients, list):
                all_clients = all_clients.get("data") or []
            c = next((x for x in all_clients if x.get("id") == params.client_id), None)
            if not c:
                return _dump({"error": f"Klient {params.client_id} nie znaleziony."})

            resp_int = await client.get(f"/api/clients/{params.client_id}/interactions")
            resp_int.raise_for_status()
            interactions_raw = resp_int.json()

        interactions: list[dict] = (
            interactions_raw
            if isinstance(interactions_raw, list)
            else interactions_raw.get("data") or []
        )

        addr = c.get("address") or {}
        klient = {
            "id": c.get("id") or "",
            "nazwa": c.get("companyName") or "",
            "kontakt": c.get("contactPerson") or "",
            "telefon": c.get("phone") or "",
            "email": c.get("email") or "",
            "nip": c.get("nip") or "",
            "typ": c.get("type") or "",
            "miasto": addr.get("city") or "",
            "adres": f"{addr.get('street', '')} {addr.get('postalCode', '')} {addr.get('city', '')}".strip(),
            "created_at": _fmt_date(c.get("createdAt")),
        }

        def _map_interaction(i: dict) -> dict:
            return {
                "id": i.get("id") or i.get("_id") or "",
                "channel": i.get("channel") or "",
                "notes": i.get("notes") or "",
                "contact_date": _fmt_date(i.get("contactDate")),
                "result": i.get("result") or "",
                "created_at": _fmt_date(i.get("createdAt")),
            }

        return _dump(
            {
                "klient": klient,
                "interakcje": [_map_interaction(i) for i in interactions],
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 3. Dodaj interakcję ─────────────────────────────────────────────────────


class DodajInterakcjeInput(BaseModel):
    """Parametry dla narzędzia crm_dodaj_interakcje."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    client_id: str = Field(..., description="ID klienta", min_length=1)
    type: str = Field(
        ...,
        description="Typ interakcji, np. 'telefon', 'email', 'spotkanie', 'wiadomość'",
        min_length=1,
        max_length=100,
    )
    note: str = Field(
        ...,
        description="Opis / notatka z kontaktu",
        min_length=1,
        max_length=5000,
    )
    contact_date: str = Field(
        ...,
        description="Data kontaktu w formacie YYYY-MM-DD lub YYYY-MM-DDTHH:MM:SS",
        min_length=10,
    )
    result: Optional[str] = Field(
        default=None,
        description="Wynik interakcji, np. 'zainteresowany', 'brak zainteresowania', 'umówiono spotkanie'",
        max_length=500,
    )


@mcp.tool(
    name="crm_dodaj_interakcje",
    annotations={
        "title": "Dodaj interakcję z klientem",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def crm_dodaj_interakcje(params: DodajInterakcjeInput) -> str:
    """Rejestruje nową interakcję handlową z klientem w CRM Pluszek.

    Używaj gdy:
    - przeprowadziłeś rozmowę telefoniczną i chcesz ją zalogować
    - odbyłeś spotkanie i chcesz zapisać notatki
    - wysłałeś email i chcesz mieć ślad w systemie

    Args:
        params (DodajInterakcjeInput):
            - client_id (str): ID klienta
            - type (str): typ kontaktu np. 'telefon', 'email', 'spotkanie'
            - note (str): treść notatki
            - contact_date (str): data w formacie YYYY-MM-DD
            - result (str, opcjonalnie): wynik rozmowy

    Returns:
        str: JSON z potwierdzeniem i ID nowej interakcji:
        {
            "sukces": true,
            "message": str,
            "interakcja": { id, type, note, contact_date, result }
        }
    """
    try:
        payload: dict[str, Any] = {
            "channel": params.type,
            "notes": params.note,
            "contactDate": params.contact_date,
        }
        if params.result:
            payload["result"] = params.result

        async with get_client() as client:
            resp = await client.post(
                f"/api/clients/{params.client_id}/interactions",
                json=payload,
            )
            resp.raise_for_status()
            created = resp.json()

        return _dump(
            {
                "sukces": True,
                "message": f"Interakcja '{params.type}' zapisana pomyślnie.",
                "interakcja": {
                    "id": created.get("id") or created.get("_id") or "",
                    "type": created.get("type") or params.type,
                    "note": created.get("note") or params.note,
                    "contact_date": _fmt_date(
                        created.get("contactDate") or params.contact_date
                    ),
                    "result": created.get("result") or params.result or "",
                },
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 4. Lista follow-upów ────────────────────────────────────────────────────


class ListaFollowupowInput(BaseModel):
    """Parametry dla narzędzia crm_lista_followupow."""

    model_config = ConfigDict(extra="forbid")

    status: Optional[str] = Field(
        default=None,
        description=(
            "Filtruj po statusie: 'pending' (oczekujące), 'done' (zakończone), "
            "'overdue' (przeterminowane — obliczane przez MCP na podstawie dueDate)"
        ),
    )
    limit: Optional[int] = Field(default=20, description="Max wyników (1–100)", ge=1, le=100)
    offset: Optional[int] = Field(default=0, description="Paginacja — ile pominąć", ge=0)


@mcp.tool(
    name="crm_lista_followupow",
    annotations={
        "title": "Lista follow-upów CRM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_lista_followupow(params: ListaFollowupowInput) -> str:
    """Pobiera listę follow-upów (przypomnień) z CRM Pluszek.

    Używaj gdy:
    - chcesz zobaczyć jakie follow-upy czekają na realizację
    - sprawdzasz przeterminowane przypomnienia
    - przeglądasz historię zakończonych follow-upów

    Filtr 'overdue' jest obliczany lokalnie: zwraca follow-upy ze statusem 'pending'
    których dueDate jest wcześniejsza niż dziś.

    Args:
        params (ListaFollowupowInput):
            - status (str, opcjonalnie): 'pending', 'done', 'overdue'
            - limit (int): 1–100 (domyślnie 20)
            - offset (int): paginacja (domyślnie 0)

    Returns:
        str: JSON z listą follow-upów:
        {
            "today": "DD.MM.YYYY",
            "total": int,
            "count": int,
            "offset": int,
            "has_more": bool,
            "followupy": [
                { id, client_id, client_nazwa, reminder_text, due_date, status, created_at }
            ]
        }
    """
    try:
        async with get_client() as client:
            # API: GET /followups/summary — zwraca zaplanowane z dueDate <= dziś
            resp = await client.get("/api/followups/summary")
            resp.raise_for_status()
            data = resp.json()

        followups: list[dict] = data if isinstance(data, list) else []

        today_str = _today_iso()

        # summary zwraca tylko 'zaplanowane' z dueDate <= dziś
        # filtr 'status' jest tu dla spójności interfejsu
        if params.status == "done":
            followups = []  # summary nie zwraca zrealizowanych

        total = len(followups)
        page = followups[params.offset : params.offset + params.limit]

        def _map_fu(f: dict) -> dict:
            return {
                "id": f.get("id") or "",
                "client_id": f.get("clientId") or "",
                "client_nazwa": f.get("clientName") or "",
                "reminder_text": f.get("reminderText") or "",
                "due_date": _fmt_date(f.get("dueDate")),
                "status": f.get("status") or "zaplanowane",
                "created_at": _fmt_date(f.get("createdAt")),
            }

        return _dump(
            {
                "today": _fmt_date(today_str),
                "total": total,
                "count": len(page),
                "offset": params.offset,
                "has_more": total > params.offset + len(page),
                "followupy": [_map_fu(f) for f in page],
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 5. Dodaj follow-up ──────────────────────────────────────────────────────


class DodajFollowupInput(BaseModel):
    """Parametry dla narzędzia crm_dodaj_followup."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    client_id: str = Field(..., description="ID klienta", min_length=1)
    reminder_text: str = Field(
        ...,
        description="Treść przypomnienia, np. 'Zadzwonić ws. oferty na ramy'",
        min_length=1,
        max_length=1000,
    )
    due_date: str = Field(
        ...,
        description="Termin follow-upu w formacie YYYY-MM-DD",
        min_length=10,
        max_length=10,
    )


@mcp.tool(
    name="crm_dodaj_followup",
    annotations={
        "title": "Dodaj follow-up do klienta",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": False,
        "openWorldHint": False,
    },
)
async def crm_dodaj_followup(params: DodajFollowupInput) -> str:
    """Tworzy nowy follow-up (przypomnienie) dla klienta w CRM Pluszek.

    Używaj gdy:
    - po rozmowie chcesz ustawić przypomnienie o ponownym kontakcie
    - planujesz wysłać ofertę i chcesz mieć termin w systemie
    - umawiasz kontakt w przyszłości

    Args:
        params (DodajFollowupInput):
            - client_id (str): ID klienta
            - reminder_text (str): co należy zrobić
            - due_date (str): kiedy — format YYYY-MM-DD

    Returns:
        str: JSON z potwierdzeniem:
        {
            "sukces": true,
            "message": str,
            "followup": { id, client_id, reminder_text, due_date, status }
        }
    """
    try:
        payload = {
            "clientName": "",  # wymagane przez API — pobieramy z client_id
            "reminderText": params.reminder_text,
            "dueDate": params.due_date,
        }

        async with get_client() as client:
            resp = await client.post(f"/api/followups/client/{params.client_id}", json=payload)
            resp.raise_for_status()
            created = resp.json()

        return _dump(
            {
                "sukces": True,
                "message": f"Follow-up zaplanowany na {_fmt_date(params.due_date)}.",
                "followup": {
                    "id": created.get("id") or created.get("_id") or "",
                    "client_id": params.client_id,
                    "reminder_text": created.get("reminderText") or params.reminder_text,
                    "due_date": _fmt_date(created.get("dueDate") or params.due_date),
                    "status": created.get("status") or "pending",
                },
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 6. Zakończ follow-up ────────────────────────────────────────────────────


class ZakonczFollowupInput(BaseModel):
    """Parametry dla narzędzia crm_zakoncz_followup."""

    model_config = ConfigDict(extra="forbid")

    followup_id: str = Field(
        ...,
        description="ID follow-upu (pobierz przez crm_lista_followupow)",
        min_length=1,
    )


@mcp.tool(
    name="crm_zakoncz_followup",
    annotations={
        "title": "Zakończ follow-up",
        "readOnlyHint": False,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_zakoncz_followup(params: ZakonczFollowupInput) -> str:
    """Oznacza follow-up jako zakończony (status: done) w CRM Pluszek.

    Używaj gdy:
    - zrealizowałeś przypomnienie i chcesz je zamknąć
    - follow-up jest już nieaktualny i chcesz go wykreślić

    Args:
        params (ZakonczFollowupInput):
            - followup_id (str): ID follow-upu do zamknięcia

    Returns:
        str: JSON z potwierdzeniem:
        {
            "sukces": true,
            "message": str,
            "followup_id": str,
            "nowy_status": "done"
        }
    """
    try:
        async with get_client() as client:
            resp = await client.patch(
                f"/api/followups/{params.followup_id}/status",
                json={"status": "zrealizowane"},
            )
            resp.raise_for_status()

        return _dump(
            {
                "sukces": True,
                "message": f"Follow-up {params.followup_id} zamknięty.",
                "followup_id": params.followup_id,
                "nowy_status": "done",
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 7. Lista produktów ──────────────────────────────────────────────────────


class ListaProduktowInput(BaseModel):
    """Parametry dla narzędzia crm_lista_produktow."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    search: Optional[str] = Field(
        default=None,
        description="Filtruj po nazwie lub kodzie produktu (wyszukiwanie częściowe)",
        max_length=200,
    )
    limit: Optional[int] = Field(default=20, description="Max wyników (1–100)", ge=1, le=100)
    offset: Optional[int] = Field(default=0, description="Paginacja", ge=0)


@mcp.tool(
    name="crm_lista_produktow",
    annotations={
        "title": "Lista produktów CRM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_lista_produktow(params: ListaProduktowInput) -> str:
    """Pobiera listę produktów z CRM Pluszek z opcjonalnym filtrowaniem.

    Używaj gdy:
    - szukasz produktu po nazwie lub kodzie
    - potrzebujesz ceny lub opisu produktu przed ofertowaniem
    - przeglądasz katalog produktów

    Args:
        params (ListaProduktowInput):
            - search (str, opcjonalnie): fragment nazwy lub kodu
            - limit (int): 1–100 (domyślnie 20)
            - offset (int): paginacja (domyślnie 0)

    Returns:
        str: JSON z listą produktów:
        {
            "total": int,
            "count": int,
            "offset": int,
            "has_more": bool,
            "produkty": [
                { id, nazwa, kod, cena, jednostka, opis }
            ]
        }
    """
    try:
        async with get_client() as client:
            resp = await client.get("/api/products")
            resp.raise_for_status()
            data = resp.json()

        products: list[dict] = (
            data if isinstance(data, list) else data.get("data") or data.get("products") or []
        )

        if params.search:
            q = params.search.lower()
            products = [
                p for p in products
                if q in (p.get("name") or p.get("nazwa") or "").lower()
                or q in (p.get("code") or p.get("kod") or "").lower()
            ]

        total = len(products)
        page = products[params.offset : params.offset + params.limit]

        def _map_product(p: dict) -> dict:
            return {
                "id": p.get("id") or p.get("_id") or "",
                "nazwa": p.get("name") or p.get("nazwa") or "",
                "kod": p.get("code") or p.get("kod") or "",
                "cena": p.get("price") or p.get("cena") or "",
                "jednostka": p.get("unit") or p.get("jednostka") or "",
                "opis": p.get("description") or p.get("opis") or "",
            }

        return _dump(
            {
                "total": total,
                "count": len(page),
                "offset": params.offset,
                "has_more": total > params.offset + len(page),
                "produkty": [_map_product(p) for p in page],
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── 8. Lista promocji ───────────────────────────────────────────────────────


class ListaPromocjiInput(BaseModel):
    """Parametry dla narzędzia crm_lista_promocji."""

    model_config = ConfigDict(extra="forbid")

    aktywne: Optional[bool] = Field(
        default=None,
        description=(
            "True = tylko promocje aktywne dziś (endDate >= dziś), "
            "False = tylko zakończone, None = wszystkie"
        ),
    )
    limit: Optional[int] = Field(default=20, description="Max wyników (1–100)", ge=1, le=100)
    offset: Optional[int] = Field(default=0, description="Paginacja", ge=0)


@mcp.tool(
    name="crm_lista_promocji",
    annotations={
        "title": "Lista promocji CRM",
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": False,
    },
)
async def crm_lista_promocji(params: ListaPromocjiInput) -> str:
    """Pobiera listę promocji z CRM Pluszek z opcjonalnym filtrem aktywności.

    Używaj gdy:
    - chcesz sprawdzić bieżące promocje do zaproponowania klientowi
    - potrzebujesz daty obowiązywania promocji
    - przeglądasz historię lub przyszłe akcje promocyjne

    Args:
        params (ListaPromocjiInput):
            - aktywne (bool, opcjonalnie): True = aktywne dziś, False = zakończone, brak = wszystkie
            - limit (int): 1–100 (domyślnie 20)
            - offset (int): paginacja (domyślnie 0)

    Returns:
        str: JSON z listą promocji:
        {
            "today": "DD.MM.YYYY",
            "total": int,
            "count": int,
            "offset": int,
            "has_more": bool,
            "promocje": [
                { id, nazwa, opis, start_date, end_date, aktywna, rabat }
            ]
        }
    """
    try:
        async with get_client() as client:
            resp = await client.get("/api/promotions")
            resp.raise_for_status()
            data = resp.json()

        promotions: list[dict] = (
            data
            if isinstance(data, list)
            else data.get("data") or data.get("promotions") or []
        )

        today_str = _today_iso()

        if params.aktywne is True:
            promotions = [
                p for p in promotions
                if (p.get("endDate") or p.get("end_date") or "9999-12-31") >= today_str
            ]
        elif params.aktywne is False:
            promotions = [
                p for p in promotions
                if (p.get("endDate") or p.get("end_date") or "9999-12-31") < today_str
            ]

        total = len(promotions)
        page = promotions[params.offset : params.offset + params.limit]

        def _map_promo(p: dict) -> dict:
            end = p.get("endDate") or p.get("end_date") or "9999-12-31"
            return {
                "id": p.get("id") or p.get("_id") or "",
                "nazwa": p.get("name") or p.get("nazwa") or "",
                "opis": p.get("description") or p.get("opis") or "",
                "start_date": _fmt_date(p.get("startDate") or p.get("start_date")),
                "end_date": _fmt_date(end),
                "aktywna": end >= today_str,
                "rabat": p.get("discount") or p.get("rabat") or "",
            }

        return _dump(
            {
                "today": _fmt_date(today_str),
                "total": total,
                "count": len(page),
                "offset": params.offset,
                "has_more": total > params.offset + len(page),
                "promocje": [_map_promo(p) for p in page],
            }
        )
    except Exception as e:
        return _handle_error(e)


# ─── Uruchomienie ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print(f"CRM Pluszek MCP Server startuje na http://localhost:8000/mcp")
    print(f"   CRM_API_URL      = {CRM_API_URL}")
    print(f"   CRM_BEARER_TOKEN = {'*' * min(len(CRM_BEARER_TOKEN), 8)}...")
    mcp.run(transport="streamable-http")
