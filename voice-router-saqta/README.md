# Saqta Voice Router — HackAlem AI

MVP голосового AI-робота для кейса **Voice Router**. Главный компонент — LLM-маршрутизатор по 40 сценариям Saqta Insurance с RU/KK/mixed speech, multi-intent и supervisor trace.

## Что уже есть в v0.1

- 40 сценариев + системные intents из исходного `scenarios.json`
- LLM routing по `description`, `not_this_if` и bilingual examples
- Structured Output для стабильного JSON
- session state: язык, active scenarios, slots, history
- веб-интерфейс с микрофоном и текстовым fallback
- STT через OpenAI Audio API
- TTS через OpenAI Audio API
- trace panel: scenario, confidence, alternatives, reason, slots, latency
- dev-evaluator на 104 высказываниях
- Dockerfile / docker compose и запуск одной командой

> Важно: v0.1 фокусируется на главном критерии — маршрутизации. Полный scenario executor с реализацией всех mock actions — следующий этап.

## Быстрый старт

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

В `.env` вставьте `OPENAI_API_KEY`.

```powershell
run.bat
```

Откройте: `http://localhost:8000`

### macOS / Linux

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
./run.sh
```

## Проверка маршрутизатора

Сначала прогоните 10 примеров:

```bash
python scripts/evaluate_dev.py --limit 10
```

Потом все 104:

```bash
python scripts/evaluate_dev.py
```

Ключевые метрики: `Primary accuracy`, `Full match`, `Multi recall`, median router latency.

## Архитектура v0.1

```text
Browser mic
   ↓
STT
   ↓
LLM Router ─── scenarios.json + dialog state
   ↓
Decision policy
   ↓
Grounded scenario reply
   ↓
TTS

             └── Supervisor Trace
```

## Следующие этапы

1. Довести routing accuracy на `dev_utterances.json`.
2. Реализовать scenario executor и 31 action поверх `mock_backend.json` / `knowledge_base.json`.
3. Добавить confirmation gate для необратимых действий.
4. Добавить topic stack/return.
5. Перейти с bounded audio STT на realtime/streaming для latency bonus.
6. Подготовить финальный README, demo сценарии и pitch.
