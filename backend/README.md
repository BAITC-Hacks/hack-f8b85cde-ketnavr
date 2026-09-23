# Backend для рекомендаций закупок

FastAPI-сервис читает Excel-архив поставщиков, считает рекомендуемые заказы и отдаёт JSON по контракту фронта.

## Быстрый запуск

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
New-Item -ItemType Directory -Path data -Force
Copy-Item -LiteralPath "$env:USERPROFILE\Downloads\Excel_IEK_Systeme_Electric_оформленные.zip" -Destination data/source.zip
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Проверь:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/data/summary
Invoke-RestMethod http://127.0.0.1:8000/ai/status
Invoke-RestMethod 'http://127.0.0.1:8000/recommendations?limit=5&ai=false'
```

`DATA_ZIP_PATH=data/source.zip` в `.env` считается от папки `backend`.
Можно указать свой абсолютный путь. Исходный архив не входит в Git.
Полный расчёт: `/recommendations?ai=false&limit=0&include_no_order=true`.
Пошаговый запуск всего приложения и чата: [README.md](../README.md).

## API-ключи

Ключи хранятся только в `backend/.env`. Не добавляй их во frontend, `VITE_*` или Git.

NVIDIA:

```env
AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
NVIDIA_MODEL=meta/llama-3.1-8b-instruct
AI_MAX_ROWS=8
```

OpenAI:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
OPENAI_MODEL=gpt-5.6-luna
AI_MAX_ROWS=8
```

If both providers are configured, use `AI_PROVIDER=auto`. The backend tries
OpenAI first and falls back to NVIDIA if the request fails.

Если API недоступен, сервис оставляет шаблонные объяснения и не ломает демо.
`/ai/status` показывает только факт наличия ключа и модель, сам ключ никогда не возвращается.

## Что делает расчёт

- Загружает MOQ, месячные продажи, месячные остатки и товары в пути.
- Считает прогнозный дневной спрос по последним месяцам.
- Ограничивает влияние разовых пиков продаж.
- Учитывает тренд, сезонность, текущий остаток, товары в пути и срок поставки.
- Округляет рекомендуемый заказ до MOQ.
- Отдаёт `critical`, `soon` или `normal` для фронтового фильтра.
