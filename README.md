# CRM Pluszek — MCP Server

Serwer MCP (Model Context Protocol) integrujący Claude z systemem CRM Pluszek.
Pozwala Claude na bezpośrednią pracę z klientami, interakcjami, follow-upami, produktami i promocjami.

## Narzędzia (8 toolów)

| Narzędzie | Opis | Operacja |
|-----------|------|----------|
| `crm_lista_klientow` | Lista klientów z filtrowaniem i paginacją | GET |
| `crm_karta_klienta` | Szczegóły klienta + historia interakcji | GET |
| `crm_dodaj_interakcje` | Dodaj interakcję do klienta | POST |
| `crm_lista_followupow` | Lista follow-upów (pending/done/overdue) | GET |
| `crm_dodaj_followup` | Utwórz nowy follow-up | POST |
| `crm_zakoncz_followup` | Oznacz follow-up jako zakończony | PATCH |
| `crm_lista_produktow` | Lista produktów z filtrowaniem | GET |
| `crm_lista_promocji` | Lista promocji (aktywne/wszystkie) | GET |

---

## Instalacja

### 1. Utwórz i aktywuj środowisko wirtualne

```bash
cd D:\DEV\APLIKACJE\crm-pluszek-mcp

python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

### 2. Zainstaluj zależności

```bash
pip install -r requirements.txt
```

---

## Konfiguracja tokenu

### Opcja A — Token z Firebase Admin SDK

1. Upewnij się, że plik klucza serwisowego istnieje:
   ```
   D:\DEV\APLIKACJE\app_crm_pluszek\CRM-Pluszek\backend\serviceAccountKey.json
   ```

2. Zainstaluj `firebase-admin`:
   ```bash
   pip install firebase-admin
   ```

3. Otwórz `generate_token.py` i uzupełnij `SERVICE_USER_UID` (UID z Firebase Console → Authentication → Users).

4. Uruchom skrypt:
   ```bash
   python generate_token.py
   ```

5. Skopiuj wygenerowany token.

### Opcja B — Token z Firebase Console / backendu

Zaloguj się do aplikacji CRM i skopiuj token z nagłówka `Authorization` w DevTools → Network.

---

## Konfiguracja .env

Skopiuj `.env.example` jako `.env` i uzupełnij:

```bash
copy .env.example .env
```

Edytuj `.env`:

```env
CRM_API_URL=https://crm.pluszek.pl
CRM_BEARER_TOKEN=wklej_tu_swoj_token
```

---

## Uruchomienie serwera

```bash
# Aktywuj venv jeśli nie jest aktywny
.venv\Scripts\activate

# Uruchom serwer MCP
python src/server.py
```

Serwer startuje pod adresem: `http://localhost:8000/mcp`

---

## Test przez MCP Inspector

```bash
npx @modelcontextprotocol/inspector http://localhost:8000/mcp
```

Sprawdź czy widoczne są wszystkie 8 narzędzi.

---

## Podłączenie do Cowork (Claude Desktop)

1. Otwórz ustawienia Claude Desktop → MCP Servers.
2. Dodaj nowy serwer:
   - **Name**: `crm-pluszek`
   - **URL**: `http://localhost:8000/mcp`
   - **Transport**: Streamable HTTP

Alternatywnie w `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "crm-pluszek": {
      "url": "http://localhost:8000/mcp",
      "transport": "streamable-http"
    }
  }
}
```

---

## Struktura projektu

```
crm-pluszek-mcp\
├── src\
│   └── server.py          ← główny serwer MCP (FastMCP)
├── generate_token.py       ← generator tokenu Firebase
├── requirements.txt        ← zależności Python
├── .env.example            ← szablon konfiguracji
├── .env                    ← konfiguracja lokalna (nie w git!)
├── .gitignore
└── README.md
```

---

## Rozwiązywanie problemów

**`RuntimeError: Brak zmiennej środowiskowej CRM_BEARER_TOKEN`**
→ Uzupełnij `.env` lub ustaw zmienną środowiskową systemowo.

**`Błąd autoryzacji (401)`**
→ Token wygasł. Wygeneruj nowy przez `generate_token.py`.

**`Nie można połączyć się z CRM`**
→ Sprawdź `CRM_API_URL` w `.env` i czy backend CRM jest uruchomiony.

**`Błąd walidacji danych (422)`**
→ Sprawdź format daty (wymagany: `YYYY-MM-DD`) lub inne pole wejściowe.
