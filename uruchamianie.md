# Uruchamianie CRM Pluszek MCP Server

## Codzienne uruchomienie

```bash
cd D:\DEV\APLIKACJE\app_crm_pluszek\crm-pluszek-mcp
.venv\Scripts\activate
python run.py
```

Serwer działa pod adresem: `http://localhost:8000/mcp`

Zatrzymanie: `Ctrl+C`

## Co robi run.py

- Odświeża token Firebase przed startem
- Uruchamia serwer MCP
- Co 55 minut automatycznie pobiera nowy token i restartuje serwer
- Jeśli serwer padnie — automatycznie go wznawia


 .venv\Scripts\activate
 python run.py