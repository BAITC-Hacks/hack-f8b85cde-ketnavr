# Quickstart

## 1. Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

В `backend/.env` укажите `DATA_ZIP_PATH`: полный путь к предоставленному архиву
`Excel_IEK_Systeme_Electric_оформленные.zip` на вашем компьютере. Сам архив в Git не включён.
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
Invoke-RestMethod "http://127.0.0.1:8000/recommendations?limit=5"
```

## 2. Frontend

В новом терминале:

```powershell
cd frontend
npm install
npm run dev
```

Открыть: `http://127.0.0.1:5173/`

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

## 4. Проверки перед push

```powershell
cd backend
.\.venv\Scripts\python.exe -m unittest discover -s tests

cd ..\frontend
npm test
npm run build
```
