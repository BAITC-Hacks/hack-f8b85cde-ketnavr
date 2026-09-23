# Quickstart

## 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

По умолчанию `DATA_ZIP_PATH=data/source.zip` относится к папке `backend`.
Положите предоставленный архив `Excel_IEK_Systeme_Electric_оформленные.zip`
в `backend/data/source.zip` или укажите свой абсолютный путь в `.env`.
Сам архив в Git не включён. Полные команды копирования есть в [README.md](README.md#шаг-2-установить-и-настроить-backend).
Для первого запуска без внешних API оставьте `AI_PROVIDER=template`.
Если `.env` уже существует, сохраните его текущие настройки и ключи.

Затем из папки `backend`:

```powershell
.\.venv\Scripts\uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Проверка:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/data/summary
Invoke-RestMethod http://127.0.0.1:8000/ai/status
Invoke-RestMethod "http://127.0.0.1:8000/recommendations?limit=5&ai=false"
```

## 2. Frontend

В новом терминале:

```powershell
cd frontend
npm install
if (-not (Test-Path .env.local)) { Copy-Item .env.example .env.local }
npm run dev
```

Открыть: `http://127.0.0.1:5173/`

В `frontend/.env.local` для запуска на одном компьютере:

```env
BACKEND_URL=http://127.0.0.1:8000
VITE_API_BASE_URL=/api
VITE_RECOMMENDATIONS_PATH=/recommendations?ai=false
VITE_DATA_MODE=api
```

Для двух ноутбуков в одной локальной сети backend запускается с
`--host 0.0.0.0 --port 8000`, а в `BACKEND_URL` указывается локальный IPv4-адрес
ноутбука с backend вместо `127.0.0.1`. Vite продолжает проксировать `/api`.
После изменения `.env.local` перезапустите frontend. Эта схема не даёт доступ через интернет.

По умолчанию backend возвращает все позиции, которым нужен заказ. В уже
существующем `backend/.env` замените `MAX_RECOMMENDATIONS=120` на
`MAX_RECOMMENDATIONS=0` и перезапустите backend. Явный параметр запроса
`limit=0` также возвращает все рекомендации, а `limit=5` ограничивает список.
`/data/summary` считает все позиции к заказу независимо от лимита.
`include_no_order=true&limit=0` возвращает также рассчитанные товары без
потребности в закупке. Frontend запрашивает полный расчёт и показывает его
в двух режимах: «К закупке» и «Весь расчёт». Фильтр «Планово» включает второй
режим и показывает товары с нулевым заказом. Отсутствие истории спроса не
считается достаточным запасом: такие строки в расчёт не включаются.

Первую проверку проведите с `ai=false`: таблица, фильтры, карточка товара и выгрузка
CSV/Excel. Затем для проверки ИИ замените параметр на `ai=true` и перезапустите
frontend. Время ожидания ответа API составляет 45 секунд. Демо включается отдельно.

## 3. API keys

Ключи вставлять только в `backend/.env`.

```env
AI_PROVIDER=nvidia
NVIDIA_API_KEY=...
AI_MAX_ROWS=8
```

или:

```env
AI_PROVIDER=openai
OPENAI_API_KEY=...
AI_MAX_ROWS=8
```

Для OpenAI с резервным NVIDIA:

```env
AI_PROVIDER=auto
OPENAI_API_KEY=...
NVIDIA_API_KEY=...
AI_MAX_ROWS=8
```

Frontend не должен видеть эти ключи.

После настройки провайдера перезапустите backend и нажмите «Спросить ИИ».
Таблицу можно оставить с `ai=false`: чат использует отдельный POST и всё
равно обращается к модели. Для локального запуска на 8000/5173 флаг
`SHARE_CHAT_ENABLED` не нужен; для сервера показа на 8010 он должен быть `true`.
Каждый вопрос может расходовать токены. Полная инструкция и проверочный
вопрос: [README.md](README.md#шаг-5-включить-чат-помощник).

## 4. Проверки перед push

```powershell
cd backend
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m unittest discover -s tests

cd ..\frontend
npm test
npm run build
```

## 5. Временная общая ссылка

Порядок запуска отдельной версии для показа команде: [SHARING.md](SHARING.md).
Она отдаёт сохранённый результат расчёта; обновления страницы не вызывают платные API.
