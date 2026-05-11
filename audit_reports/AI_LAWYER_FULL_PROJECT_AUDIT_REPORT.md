# AI_LAWYER FULL PROJECT AUDIT REPORT

**Режим:** только чтение и диагностика (ингест/apply не запускались; `rag/` и `staging/` не изменялись этим аудитом).  
**Дата аудита:** 2026-05-07 (среда).  
**Машинные данные:** полный скан `rag/` и smoke `search()` сохранены в `audit_reports/_audit_scan_raw.json` (генератор-скрипт после прогона удалён по правилам аудита).

---

## 0. Executive summary

| Тема | Вывод |
|------|--------|
| **Стадия** | Крупный **монолитный прототип → кандидат в MVP**: Telegram-сценарии + большой локальный RAG + grounded-поиск; продакшен не готов. |
| **Папок-источников под `rag/`** (без `rag_backup*`) | **65** |
| **Всего JSON в корпусе** (исключая служебные имена отчётов в скрипте) | **8428** |
| **Условно «кодексы»** (имена без `kz_law_`, без `vs_np`, без `router`) | **18** папок |
| **Законы `kz_law_*`** | **31** папка |
| **НП ВС `kz_vs_np_*`** | **13** папок |
| **Роутеры-плейсхолдеры** (`*_router_code`, 0 JSON) | **3** |
| **`search()` без LLM** | Работает; массовый smoke: **71 OK / 5 FAIL** из **76** запросов (см. §6). |
| **Direct RAG answer (`build_direct_rag_answer`)** | Работает для статей и для НП ВС после нормализации результата `search()` (проверено 5 кейсов). |
| **LLM layer** | **Сломан** вызов в этой среде (**нет `client.responses`**); **`rag-query`** при ошибке модели может уйти в **direct excerpt**, Telegram **`rag_lookup`** — только текст ошибки. |
| **Telegram / UX** | ReplyKeyboard по константам из `main_menu.py`; сценарии регистрируются **до** fallback `strict_rag_lookup`; при ошибке LLM пользователь получает текст ошибки (не тишина). Inline callbacks не найдены по grep — UX завязан на текст кнопок и произвольный текст → RAG. |
| **Главные риски** | (1) LLM сломан из‑за API клиента; (2) **КоАП JSON лежит внутри `kz_appc_code`** (известный дубликат doc_id); (3) **пустые/битые JSON** и **пустой текст статей** в части файлов; (4) рассинхрон canon ↔ rag (**роутеры без папок**, лишние **`kz_gk__code` / `kz_tk__code`**); (5) огромный незакоммиченный diff — регрессии не изолированы. |
| **Что чинить первым (не делалось)** | Зафиксировать версию `openai` под `client.responses.create` или переписать вызов под поддерживаемый SDK; починить дубликат КоАП в АППК и мусорные имена папок; вычистить 12 повреждённых JSON; выровнять `canon_sources` vs реальные папки. |

---

## 1. Git / workspace status

Команды: `git status --short`, `git diff --stat`.

**Наблюдение:** рабочая копия **очень загрязнена**: десятки изменённых файлов сценариев, **новые каталоги** (`app/retriever/`, `app/ingest/`, большие части `rag/`, `staging/`, `scripts/`, `docs/` и т.д.) помечены как **неотслеживаемые (`??`)**. Коммитов в ходе аудита не делалось.

**Изменённые отслеживаемые файлы (важное для RAG/роутинга):**

- `index/root_index/root_index.json` — **+228 строк** (расширение канона / аббревиатур).
- `main.py` — существенные изменения (+164 строк net в статистике diff).
- `app/retrivier/rag_retriever.py` — опечатка в имени пути `retrivier`; большой diff (параллельно есть **`app/retriever/`** как новый пакет).

**Прочее:** массовые правки `app/features/*`, `app/shared/llm_client.py`, `exports/*.docx`; удалены `app/features/petitions/verifier_*.py`, `app/services/contract_pipeline.py`.

**`rag/` и `staging/`:** в `git status` присутствуют как **неотслеживаемые** деревья (не считаются «изменением tracked файла», но это главный объём данных).

---

## 2. Project structure audit

**Верхний уровень (ключевое):**

| Область | Назначение |
|---------|------------|
| `app/retriever/` | **`search()`**, хард-роуты источников, `_source_hints` (канон для strict-поиска). |
| `app/shared/rag_prompt_builder.py` | **Prompt builder**, `NOT_FOUND_MESSAGE`, `build_direct_rag_answer`, `build_grounded_rag_prompt`, парсинг запроса. |
| `app/shared/handlers/rag_lookup.py` | Telegram: fallback поиск по **любому тексту** после сценариев → LLM. |
| `app/shared/llm_client.py` | **OpenAI Responses API** (`client.responses.create`). |
| `app/bot/main.py` | Регистрация роутеров Aiogram, `TELEGRAM_BOT_TOKEN` из env. |
| `app/ingest/` | Извлечение текста, сплит статей/пунктов, валидация JSON, diff. |
| `scripts/` | `import_code_to_staging.py`, `import_vs_np_to_staging.py`, `diff_rag_batch.py`, `approve_rag_batch.py`, `debug_docx_text.py`, `ingest_source.py` и др. |
| `rag/` | Локальная библиотека JSON по `source_id`. |
| `staging/` | Батчи перед approve/apply. |
| `index/root_index/root_index.json` | Канон источников и фиксированные названия для роутера. |
| `main.py` | CLI: загрузка индексов + **`python main.py rag-query "..."`**. |

**Тесты:** каталога `tests/` с pytest-кейсами **не обнаружено**; модуль **`pytest` не установлен** (`python -m pytest` → `No module named pytest`).

---

## 3. RAG inventory audit

Источник строк ниже: **`audit_reports/_audit_scan_raw.json`**, поле `per_folder` (+ ручная группировка имён).

### 3.1 Codes (примеры реальных папок под `rag/`)

`kz_constitution_2026`, `kz_gpk_code`, `kz_family_code`, `kz_budget_code`, `kz_land_code`, `kz_health_code`, `kz_ecology_code`, `kz_social_code`, `kz_gk__code` ⚠ (опечаточное имя), `kz_tm_code`, `kz_koap_code`, `kz_appc_code`, `kz_nk_code`, `kz_pk_code`, `kz_uk_code`, `kz_tk__code` ⚠, и др.

### 3.2 Laws (`kz_law_*`)

31 папка, в т.ч.: `kz_law_legal_acts_code`, `kz_law_payments_systems_code`, `kz_law_foreigners_status_code`, `kz_law_bankruptcy_code`, `kz_law_mortgage_code`, `kz_law_permits_notifications_code`, `kz_law_architecture_construction_code`, `kz_law_advocacy_legal_aid_code`, … (полный список — в JSON).

### 3.3 VS NP / judicial guidance

13 папок `kz_vs_np_*`, включая: labor, koap general part, civil interim, consumer, moral damage, admin court decision, civil court costs, civil disputes practice, civil judgment, civil procedure norms, invalidity transactions, llp/alp, public procurement — все с **`doc_type: judicial_guidance`** в выборке.

### Сводная таблица по папкам (укороченная)

Полная построчная таблица из запроса пользователя **слишком велика** для отчёта; см. **`audit_reports/_audit_scan_raw.json`**. Ниже — агрегированный статус сканера (поля обрезаны до 25 примеров на тип проблемы **на папку**, поэтому некоторые счётчики — **нижняя граница**):

| source_id (folder) | json_count | doc_type (top) | granularity | status (эвристика сканера) |
|-------------------|-----------:|----------------|-------------|-----------------------------|
| kz_law_advocacy_legal_aid_code | 106 | law_article | article | GREEN |
| kz_law_architecture_construction_code | 114 | law_article | article | GREEN |
| kz_social_code | 272 | code_article | article | GREEN |
| kz_ecology_code | 418 | code_article | article | GREEN |
| kz_gpk_code | 495 | code_article | article | GREEN |
| kz_koap_code | 995 | code | article | RED (parse_errors, fn mismatch, empty text samples, dup art#, no hash) |
| kz_appc_code | 193 | code | article | RED (+ **файлы `kz_koap_ch1_art*.json`**) |
| kz_nk_code | 846 | code | article | RED |
| kz_gk__code | 411 | code | article | RED |
| kz_tk__code | 549 | code | article | RED |
| kz_*_router_code | 0 | — | — | RED (нет файлов — ожидаемо как заглушки) |
| kz_vs_np_* (point) | 13–36 each | judicial_guidance | point | в основном GREEN |

**Обнаружено дубликатов `doc_id` между разными папками:** **9** групп (ключевой пример в JSON):

- `kz_koap_ch1_art1` … `kz_koap_ch1_art5` одновременно в **`kz_appc_code`** и **`kz_koap_code`**.

**Файлы с «коап» в имени внутри АППК:**  
`kz_koap_ch1_art1.json` … `kz_koap_ch1_art5.json`.

---

## 4. RAG data quality audit

Сводка по **обнаруженным в сканере** проблемам (суммы по усечённым спискам на папку — см. оговорку в §3):

| issue_type | count (floor / recorded) | affected_sources (примеры) | examples |
|------------|--------------------------|----------------------------|----------|
| Непарсируемый JSON | **12** записей | `kz_appc_code`, `kz_koap_code`, `kz_gk__code`, `kz_vs_np_civil_judgment_code`, … | `kz_appc_ch2_art6.json: Expecting value line 1` |
| Пустой текст статьи | **≥73** (усечённые списки) | `kz_koap_code`, `kz_enforcement`, нотариат, торговля, … | попадает в `empty_article_text` |
| Filename ≠ doc_id | **≥61** | GK/KoAP/NK/PK/TK «двойное подчёркивание», законы | валидатор `filename_doc_id_mismatch` |
| Нет / пустой `text_hash` | **≥721** | почти все кодексы и часть законов | поле отсутствует или пустое |
| Дубликаты номера статьи в одном источнике | есть | `kz_appc_code`, `kz_koap_code`, `kz_nk_code`, … | поле `duplicate_article_numbers` в JSON по папкам |
| Mojibake (`validate_rag_json`) | **0** срабатываний | — | — |
| Символ замены `` | **0** | — | — |
| Неверный `notes` (не list) | **0** | — | — |

**Отдельно:** подтверждено наличие **«known cross-source duplicate / wrong folder»**: фрагмент КоАП лежит в **`kz_appc_code`** (совпадающие `doc_id` с `kz_koap_code`).

---

## 5. Index / root_index audit

Файл: `index/root_index/root_index.json`.

| Проверка | Результат |
|----------|-----------|
| Записей в `canon_sources` | **66** |
| Папок `kz_*` под `rag/` (без backup) | **65** |
| В каноне, но **нет папки** в `rag/` | **`kz_bankruptcy_router_code`**, **`kz_petitions_router_code`**, **`kz_upk_code`** |
| Папка есть в `rag/`, но **нет в каноне** | **`kz_gk__code`**, **`kz_tk__code`** (ошибочные/legacy имена) |
| Новые законы social / mortgage / permits / architecture / advocacy | В каноне и папки присутствуют (**проверено по списку папок** в JSON). |

Неправильные названия / дубли внутри `fixed_abbreviations` — **не разбирались автоматически** (объём); очевидная проблема — **лишние дисковые папки с `__`**.

---

## 6. Search/routing audit

Метод: **`search()` без LLM**, **76** фиксированных русских запросов (коды, законы, НП ВС, «999»).

**Итог:** **71 OK**, **5 FAIL**, **0** исключений.

**FAIL (все: `result_count == 0`):**

| query (суть) | expected source | note |
|--------------|-----------------|------|
| Статья 1 **АППК РК** | `kz_appc_code` | Известная проблема данных/роутинга — **не чинили** по ТЗ. |
| Статья **29** Закона о реабилитации и банкротстве | `kz_law_bankruptcy_code` | В корпусе может не быть ст. 29 или формулировка запроса не матчится — нужна проверка наличия статьи в JSON (не делалась). |
| Пункт **19** НП ВС общей части КоАП | `kz_vs_np_koap_general_part_code` | Нет матча (нет пункта или триггеры НП). |
| Пункт **11** НП ВС обеспечительных мерах | `kz_vs_np_civil_interim_measures_code` | То же. |
| Пункт **12** НП ВС защите прав потребителей | `kz_vs_np_consumer_protection_code` | То же. |

Остальные запросы из списка (СК, ГК, ГПК, КоАП ст.1, экология 418, соцкод 10-1/263, правовые акты, платежи, иностранцы, ипотека, разрешения, архитектура, адвокатура, большинство НП ВС, ст. 999 ипотеки, пункт 999 трудового НП) — **`ok: true`** в машинном логе.

Полная таблица: **`audit_reports/_audit_scan_raw.json` → `smoke_search`**.

---

## 7. Direct answer / prompt builder audit

Файл: `app/shared/rag_prompt_builder.py`.

| Требование | Статус |
|------------|--------|
| `NOT_FOUND_MESSAGE = "Информация не найдена в базе данных"` | **Да** (строго это значение). |
| Статьи → «статья N» в `_article_label` | **Да**. |
| НП ВС point → «пункт N» | **Да** для `judicial_guidance` + `granularity==point`. |
| Нет формулировки «НП ВС, статья N» для point | **Да** (используется «пункт»). |
| Пустой поиск → NOT_FOUND через `build_direct_rag_answer` | **Да** (`strip()` → сообщение). |

**5 прогонов без LLM:**

1. Закон ипотеки ст. **999** → `[]` → ответ **== NOT_FOUND_MESSAGE**. ✅  
2. НП ВС труд, пункт **999** → `[]` → **== NOT_FOUND_MESSAGE**. ✅  
3. Ипотека ст. **1** → `kz_law_mortgage_code`, текст начинается с названия закона. ✅  
4. СК ст. **1** → `kz_family_code`. ✅  
5. НП ВС труд п. **1** → `kz_vs_np_labor_disputes_code`, текст непустой. ✅  

---

## 8. LLM/OpenAI layer audit

- Ключ читается из **`OPENAI_API_KEY`** в `.env` через `python-dotenv` в **`app/shared/llm_client.py`** (и частично в `speech_to_text`).
- **`requirements.txt`**: `openai` **без закрепления версии** → при апдейте окружения возможна поломка API.
- Фактическая ошибка при вызове LLM в этой среде: **`AsyncOpenAI` не имеет атрибута `responses`** при `client.responses.create`.
- Для **`python main.py rag-query`** путь **`strict_rag_answer`** после ошибки LLM всё равно может вернуть **`build_direct_rag_answer`** (пустой `raw_answer` после `except`). В Telegram-хэндлере **`rag_lookup`** при ошибке LLM пользователь получает только сообщение об ошибке (**без** автоматического показа текста статей).
- **Ключ в отчёт не выводился.**

---

## 9. Telegram bot / buttons / UX audit (статический)

**Инфраструктура:** `aiogram==3.20.0`, `app/bot/main.py`.

**Меню:** только **ReplyKeyboard** из `app/shared/main_menu.py` — константы `BTN_*`; совпадение через `main_menu_button_matches` в handlers сценариев (`contracts`, `petitions`, `claims`, `consult`, `bankruptcy`, `analyze`).

**Fallback RAG:** `app/shared/handlers/rag_lookup.py`, фильтр `@router.message(F.text)`, регистрируется **последним**. Если активен FSM-сценарий → `SkipHandler`.

**Ошибка LLM:** ловится `except Exception`, пользователю уходит сообщение **«RAG найден, но LLM-ответ не сформирован»** + текст исключения (не silent crash). Прямой **`build_direct_rag_answer`** при ошибке **не вызывается** (в отличие от `main.strict_rag_answer`, где есть fallback при пустом ответе модели).

**Inline callbacks:** по проекту в **`app/`** не найдено вхождений `callback_data` / `CallbackQuery` (grep) — таблица «callback → handler» **не применима**; доминирует текст кнопок и свободный ввод.

**Токен:** `TELEGRAM_BOT_TOKEN` только из **env**, в коде хардкода не найдено.

---

## 10. CLI / main.py audit

`main.py`:

- Без аргументов: загружает **root + доменные индексы**, проверяет `storage_layout` через `check_storage_layout`, печатает **`Checks OK ✅`** — при отсутствии файлов упадёт с исключением.
- **`python main.py rag-query "<вопрос>"`**: вызывает **`asyncio.run(strict_rag_answer(q))`** → поиск → при наличии контекста вызывается **LLM**; при **исключении** или пустом ответе модели срабатывает **fallback на `build_direct_rag_answer`** (ветка `if rag_context and (not raw_answer or raw_answer == NOT_FOUND_MESSAGE)`), так что при ошибке SDK пользователь всё же может получить прямой вывод статей из RAG. В аудите **`call_llm_simple`** многократно ретраил одну и ту же ошибку — до fallback есть заметная задержка.

---

## 11. Ingest pipeline audit (чтение кода, без запуска)

| Компонент | Назначение |
|-----------|------------|
| `scripts/import_code_to_staging.py` | DOCX → JSON в `staging/codes` или **`staging/laws`**, отчёт `import_report.json`, проверка expected-min/max. |
| `scripts/import_vs_np_to_staging.py` | VS NP → staging (точечная гранулярность). |
| `scripts/diff_rag_batch.py` | Сравнение батча с `rag/<source_id>`. |
| `scripts/approve_rag_batch.py` | Копирование в `rag/` только с **`--apply`**, иначе dry-run; блок по mojibake из отчёта импорта. |
| `app/ingest/validate_rag_json.py`, `diff_checker.py` | Валидация и хеширование. |

Apply по дизайну **явный** (`--apply`), dry-run безопасен на уровне скрипта — при условии, что его не вызывают с флагом записи.

---

## 12. Compile / tests audit

| Проверка | Результат |
|----------|-----------|
| `python -m compileall -q app scripts main.py` | **OK** (без сообщений об ошибках). |
| `pytest` / `python -m pytest` | **Недоступно** — модуль не установлен; отдельных `tests/*.py` не найдено. |

---

## 13. Security audit

- Поиск по `OPENAI_API_KEY`, `TELEGRAM_BOT_TOKEN` в `app/`: только чтение через `os.getenv`, ключей в исходниках не найдено.
- Упоминается неотслеживаемый **`.env.demo`** — содержимое **не читалось**.
- Полный **`grep sk-proj` по всему дереву** в среде дал **timeout**; выборочно по `app/*.py` секретов не видно.
- **Рекомендация позже:** не коммитить `.env`, выровнять `.gitignore`.

---

## 14. Known issues list

| priority | issue | area | evidence | risk | recommended fix (позже) |
|----------|-------|------|----------|------|-------------------------|
| P0 | LLM SDK: нет `client.responses` | `llm_client.py` + зависимости | лог `rag-query`, долгие retry | Telegram-сценарии без текста статьи при ошибке; модель недоступна | Закрепить версию SDK или сменить API вызов |
| P0 | КоАП JSON внутри папки АППК | `rag/kz_appc_code` | дубликаты `doc_id`, имена `kz_koap_*` | Неверный юридический источник в выдаче | Удалить/перенести файлы, пересобрать индекс |
| P1 | Пустые/битые JSON | несколько кодексов | 12 parse errors | Дыры в базе | Переимпорт или удалить нулевые файлы |
| P1 | Рассинхрон canon ↔ rag | `root_index` | роутеры без папок; папки `gk__`/`tk__` | Путаница роутинга и ingest | Привести имена и канон к одному множеству |
| P2 | Нет автотестов | repo | нет pytest | Регресс не ловится | Добавить минимальные тесты `search()` и эталонных запросов |
| P2 | APPK ст. 1 → [] | search smoke | §6 | UX юристов | Отдельная задача (не трогали по ТЗ) |
| P3 | Огромный незакоммиченный diff | git | status | Невозможен безопасный review | Разбить на коммиты / ветки |

---

## 15. Project stage / product status

**Уже умеет:** локальный RAG по множеству кодексов и законов; judicial guidance НП ВС; strict-поиск `search()` с хард-маршрутизацией по многим актам; Telegram-сценарии (договор, заявления, претензии, консультация, банкротство, анализ); fallback текстового запроса в RAG.

**Пока не умеет стабильно:** полноценный LLM-ответ в прод-сборке без починки SDK; сквозные автотесты; чистая индексация без артефактов данных.

**MVP:** **можно показывать ограниченно** (демо RAG + сценарии), если принять отсутствие LLM или выключить его и использовать только direct excerpt.

**Юрист для тестов:** **да, частично** по поиску статей/оглавлению; **нет** для сквозного «юридического разбора» до починки LLM.

**Клиентам:** **нет** как продукту до стабилизации ключей, данных и мониторинга.

**5 шагов до стабильного MVP:** (1) починить OpenAI клиент; (2) вычистить КоАП из АППК и битые JSON; (3) синхронизировать канон и имена папок; (4) смоук-тесты `search` в CI; (5) минимальный health-check скрипт на RAG.

**5 шагов до production:** наблюдаемость, RBAC/лимиты, резервное копирование `rag/`, юридический disclaimer, вложения и SLA по качеству ответа.

---

## 16. Final conclusion

| Область | Светофор |
|---------|----------|
| RAG library health | **YELLOW** (объём большой, но есть битые файлы, дубликаты, пустой текст) |
| Search routing health | **YELLOW** (71/76 smoke OK; известные дыры по APPK и части НП) |
| LLM layer | **RED** |
| Telegram UX / buttons | **YELLOW** (архитектура здравая; при падении LLM пользователь видит ошибку; нет inline-кнопок) |
| Ingest pipeline | **GREEN** (по коду и наличию скриптов dry-run) |
| Data quality | **YELLOW / красные зоны в отдельных кодексах** |
| **Overall** | **Prototype → MVP candidate; production-ready — нет** |

---

*Конец отчёта.*
