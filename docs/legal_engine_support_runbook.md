# Legal engine — runbook для support / ops (KZ)

Кратко: как читать логи, флаги и телеметрию **без доступа к тексту пользователя** в structured-событиях.

## Переменные окружения

| Переменная | Назначение |
|------------|------------|
| `LEGAL_ENGINE` | `1` / `true` — включены policy/clarify, Stage3 `LegalRunContext` в поддерживаемых пайплайнах. |
| `LEGAL_ENGINE_TELEMETRY` | `1` / `true` — JSON-события `kind: legal_engine_telemetry` в логгер `legal_engine.telemetry`. |
| `LEGAL_ENGINE_TELEMETRY_TRACE_ID` | Внешний correlation id (обрезается до 128 символов в записи прогона). |
| `LEGAL_ENGINE_TELEMETRY_SAMPLE_RATE` | Доля прогонов с телеметрией, `0.0…1.0` (при `0` запись не стартует). |

## Как читать telemetry

Одна строка лога = один JSON-объект. Обязательные поля:

- `kind`: `legal_engine_telemetry`
- `feature`: `consult` | `claims` | `gpo` | `admin` | `contract` | `bankruptcy` | `analyze`
- `scenario_id`: под-сценарий из registry
- `stage`, `status`
- `run_id`, при наличии `trace_id`
- `event_seq`: порядок внутри прогона

**Нет** в канонических событиях: текста документа, вопросов пользователя целиком, полного тела исключений.

## Стадии прогресса (happy path)

| Stage | Смысл |
|-------|--------|
| `pipeline_enter` | Старт прогона (после sampling). |
| `rag_complete` | RAG отдал контекст; метрики: число статей, запросов, `stage3_context`. |
| `prompt_ready` | Промпт собран (где применимо). |
| `llm_complete` | Основной вывод модели получен. |
| `verify_complete` | Верификация (доменная или общая) пройдена; `repair_rounds`, `verify_ok`. |
| `pipeline_complete` | Успешное завершение; может быть `export_docx`. |

## Исходы без «исключения как контракта ответа»

| Stage | Типичный смысл |
|-------|----------------|
| `gate_blocked` | Политика остановила до генерации (жёсткий блок). |
| `clarify_selected` | Нужны уточнения; `clarify_depth`. |
| `safe_draft_selected` | Пользователь идёт в осторожный черновик. |
| `verify_failed` | Верификатор не принял текст; смотреть `outcome_code`. |
| `rag_empty` | Нет/мало RAG; для договоров — см. `outcome_code` (`contract_*`). |
| `pipeline_aborted` | Явный обрыв политикой/потоком (редко; уточнять по `outcome_code`). |

## Классы проблем (operator)

- **missing user facts** — `clarify_selected`, неполная анкета, `gate_blocked` с policy.
- **verifier fail** — `verify_failed`, часто `contract_verifier_hard` / длина договора.
- **retrieval weak** — `rag_empty`, `contract_rag_empty`, `contract_evidence_pack_insufficient`.
- **money conflict** — `verify_failed` с outcome, связанным с деньгами (иск/претензии).
- **export issue** — ошибки сохранения файла (обычно OSError в guard; может не быть полного progress).
- **scenario mismatch** — scenario lock в FSM vs профиль (реже в telemetry; чаще ValueError в логах приложения).

## Что делать support по классу

1. **Убедиться**, что у клиента есть `trace_id` и время события.  
2. Найти последние события с тем же `run_id` / `trace_id`, проверить последний `stage`.  
3. **Retrieval weak** — проверить RAG-индекс, `source_ids`, лимиты `min_articles`.  
4. **Verifier** — не просить пользователя «обойти» проверку; предложить дополнить карточку или повторить с полными данными.  
5. **Clarify** — провести пользователя по недостающим полям; не считать багом отсутствие ответа при пустых слотах.  
   
Для автоматической сводки без PII в коде: `app.shared.legal_engine.support_diagnostics.summarize_legal_engine_telemetry`.

## Коды договора (`outcome_code`, H1)

- `contract_rag_empty` — пустой RAG.  
- `contract_evidence_pack_insufficient` — мало нормализованных записей evidence pack.  
- `contract_length_gate` — текст короче порога длины.  
- `contract_verifier_hard` — жёсткая проверка текста договора.

Пользовательские сообщения начинаются с `[contract:…]` — ориентир для фильтрации в чат-поддержке.
