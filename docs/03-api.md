# 3. REST API

Базовый путь `/api`. Интерактивная спецификация со всеми JSON-схемами — `/api/docs`, машинная — `/api/openapi.json`. Все даты входа с часовым поясом; ответы UTC. GET не требует CSRF; любые изменяющие запросы требуют `Origin: APP_ORIGIN`, `Content-Type: application/json`, после входа — `X-CSRF-Token`. POST без тела отправляет `{}`. CORS не включён. Кука `__Host-killstass`: Secure, HttpOnly, SameSite=Strict, Path=/, 14 дней. CSRF возвращается после входа и в `/auth/me`; пароль, хэш и токен сессии API не возвращает.

| Метод и путь | Доступ / действие | Успех |
|---|---|---|
| GET /health | доступность БД и миграций, без сессии | 200 / 503 |
| POST /auth/register | login, optional email, display_name, password≥12; 5/15 мин/IP | 201 + csrf, cookie |
| POST /auth/login | identity (login/email), password; 15/15 мин/IP | 200 + csrf, cookie |
| GET /auth/me | текущая сессия, профиль и CSRF | 200 |
| POST /auth/logout | удаление текущей сессии | 200 |
| PATCH /profile | своё display_name | 200 |
| POST /profile/password | current_password, new_password; отзыв всех сессий, новая текущая | 200 + csrf |
| DELETE /profile | свой пароль; удаление и анонимизация | 200 |
| GET /catalogs | авторизованный; активные справочники; include_inactive=true для подписей истории | 200 |
| GET /friends | свои связи и блокировки | 200 |
| POST /friends | public_id; только существующий неблокированный не-свой аккаунт | 201 |
| POST /friends/{public_id} | accept/decline: адресат; cancel: отправитель; remove/block/unblock: своя сторона | 200 |
| GET /challenges | свои входящие/исходящие, истёкшие обновляются | 200 |
| POST /challenges | друг; request_id, public_id, edition, mission_id?, mode | 201 + id |
| POST /challenges/{uuid} | участник; request_id, action accepted/declined/cancelled | 200 + status, match_id? |
| GET /notifications | свои последние 100 уведомлений | 200 |
| POST /notifications/{id}/read | только собственное уведомление | 200 |
| GET /live-matches | свои незавершённые, максимум 100 | 200 |
| GET /matches/{uuid} | только участник, полный снимок, version | 200 |
| PUT /matches/{uuid}/setup | участник, только setup; request_id, version + параметры | 200 |
| POST /matches/{uuid}/scores | участник, только свои очки, active; request_id, version, turning_point, source_id+delta и/или cp и/или notes | 200 |
| POST /matches/{uuid}/actions | участник; request_id, version, action, turning_point? | 200 |
| GET /matches/{uuid}/audit | участник; limit 1..100, offset | 200 |
| GET /matches/{uuid}/events | участник; SSE revision каждые ~3 с при изменении | 200 stream |
| POST /quick-matches | владелец; request_id, guest_name или opponent_public_id?, local?, edition, team1_id, team2_id, mission_id, killzone_id, vp_for, vp_against, played_at, notes? | 201 + id |
| GET /history | свои учитываемые результаты, limit 1..100 default20, offset | 200 items,total |
| GET /stats | свои агрегаты, серии, разбивки и динамика | 200 |
| GET /export | свои учитываемые результаты, format=csv/json, потоковый экспорт | 200 attachment |

**Общие фильтры** history/stats/export: from_date, to_date (`YYYY-MM-DD`, включительно по Москве), opponent (имя или точный ID), team_id, mission_id, killzone_id, kind=friend/guest. Идущие/спорные матчи видны отдельно `/live-matches`, не смешиваются с завершённой историей. Списки друзей и уведомлений отражают личную информацию, чужие профили API не отдаёт.

## JSON примеры

```json
{"request_id":"540f42ea-f270-410b-bb97-74554f8859cd","version":4,"turning_point":1,"source_id":7,"delta":1}
```

CP передаётся абсолютным значением остатка, VP — дельтой; нельзя записывать очки другой стороны. Каждый источник принадлежит редакции и ограничен max_per_turn. Нижняя граница VP/CP — 0. Для legacy сохраняются прежние ограничения, включая неактивные исторические источники. Для approved2025 используются замороженные caps миссии/выбранной Tac Op, максимум 6 за направление, Kill Op только вычисляемый. Гостевая запись уже содержит окончательные VP, новый бонус на неё не накладывается; для Approved Ops итог ограничен 21 VP (final_score_cap_exceeded).

```json
{"request_id":"7a0a984a-b209-499e-9fe5-be41227e944f","version":8,"action":"finish"}
```

Автомат состояний:

```text
challenge: pending -> accepted | declined | cancelled | expired
accepted -> создаётся ровно один общий матч setup
match: setup -> active -> awaiting_confirmation -> confirmed
                             └-> disputed -> active -> повторная отправка
quick: unconfirmed (терминальное состояние)
```

`start`, `finish`, `reopen` — любой участник; `confirm`, `dispute` — только не тот, кто отправил текущий результат. `turn` выбирает общий поворот в active. Изменения заблокированы до разрешения спора через reopen. Подтверждённые записи неизменяемы. Таймер вызова по умолчанию 48 ч; «expired» вычисляется при чтении/попытке ответа, фонового постоянного писателя БД нет.

**Ошибки**: 401 unauthenticated/invalid_credentials; 403 origin_forbidden/csrf_invalid/blocked/friend_required/password_invalid; 404 account_not_found/match_not_found/challenge_not_found (чужой приватный матч неотличим от отсутствующего); 409 version_conflict/idempotency_key_reused/invalid_match_transition/setup_closed; 422 ошибки Pydantic, catalog_invalid/score_out_of_range/setup_incomplete; 429 rate_limited; 413 слишком большое тело; 415 не JSON; 503 миграции/перегрузка сервера. Неожиданные 500 не раскрывают SQL в ответе, смотрите локальные логи.

**Повторы**: сохраняйте один request_id при сетевом повторе *того же* действия. Новый пользовательский клик — новый UUID. Повтор после успеха отдаёт прежний результат без повторной записи, даже если version уже выросла; другой payload с тем же ключом — 409. Не следует генерировать новый UUID при автоматическом сетевом retry. Социальные операции имеют естественную уникальность/ON CONFLICT.

**Синхронизация**: SSE передаёт только revision; клиент получает снимок REST. Резервный polling раз в 10 с. Сессия/членство перепроверяются каждые 3 с, соединение периодически обновляется. При редактировании формы чужое обновление не затирает ввод; появляется уведомление, конфликт при сохранении требует обновления страницы. Правка заметок сохраняет факт изменения в аудите, не историю текста.


## v1.1 — справка и Approved Ops

| Метод и путь | Доступ / параметры | Ответ |
|---|---|---|
| GET /reference/game-sequence?edition=2024 | Сессия обязательна; edition 2021/2024 | 200 edition,steps,retrieved_at,rules_version; ETag, private max-age=0 must-revalidate; If-None-Match → 304 |
| GET /reference/rules?edition=2024&q=... | Сессия; q до 120 символов; до 50 записей | 200 массив коротких пересказов со ссылками |
| GET /stats/tac-ops | Своя статистика, те же фильтры, что /stats | 200 tac_op_id,label,games,vp,avg_vp, включая выбранную Tac Op с нулём VP |
| POST /matches/{uuid}/primary | Участник; request_id,version,primary_op crit/tac/kill; active, TP1, ещё не зафиксирована | 200 ok, идемпотентно |
| POST /matches/{uuid}/reveal-tac | Участник; request_id,version; active approved2025 | 200 ok; ручное раскрытие в момент карточки |
| POST /matches/{uuid}/kills | Участник; request_id,version,turning_point 1..4,delta -40..40 | 200 ok; нетто-выведения только своей стороны |

`PUT setup` дополнен собственными `primary_op` (nullable, предварительный выбор), `tac_op_id` (nullable до готовности), `aspect_counts` (объект dire_avenger/howling_banshee/striking_scorpion только для условного архетипа Blades). Общие поля команды/миссии остаются прежними. Оба игрока отдельно сохраняют собственную часть. Старт approved2025 требует четыре поворота, обе Tac Op и оба исходных количества оперативников из таблицы 5–14. Основная цель фиксируется позже, в TP1; переход на TP2+ и finish требуют фиксации обоих игроков. Завершение — только при текущем TP4; принадлежность источника/лимиты проверяются и при исправлении предыдущего поворота.

В снимке матча: scoring_mode, rules_snapshot (без секретного раздела tacs), kills; у игроков raw_vp,crit,tac,kill,grade,incapacitated,primary_bonus,vp,primary_op,primary_committed,tac_op_id,tac_revealed,aspect_counts. Чужая primary_op до finish = null; чужая Tac Op = null до ручного раскрытия/первого начисления Tac VP или конца боя. Аудит primary_commit показывает только факт, не направление; live-matches вообще не отдаёт rules_snapshot. После finish обе основные цели видны одновременно. Это не URL/token-секреты, а приватные игровые решения — их не должно быть в чужом ответе до раскрытия.

`catalogs.active=false` не равно удалению. Старые имена/ID доступны с include_inactive; новые setup/quick принимают только active, а для реального пакета ещё verified. Идущий approved-матч использует свой rules_snapshot даже после деактивации/обновления карточки в справочнике. Дата справки всегда UTC в JSON; интерфейс форматирует Europe/Moscow.

Дополнительные ошибки: 401 unauthenticated; 404 reference_not_verified (например edition2021); 409 primary_closed/scoring_closed/version_conflict; 422 catalog_unverified/approved_requires_four_turns/tac_archetype_invalid/aspect_counts_invalid/player_setup_incomplete/primary_not_committed/component_cap_exceeded/source_invalid_for_pack/kills_out_of_range/finish_requires_turn_four. Все ошибки API, кроме успешных reference 200/304, имеют no-store. Сессия проверяется и перед условным ответом 304.

Машинная спецификация `docs/openapi.json` сгенерирована из фактического FastAPI app v1.1.0; `/api/openapi.json` использует тот же app. SQL-функции и поля match snapshot возвращаются как расширяемые JSON-объекты, точные поля описаны выше.

UI v1.1 использует версионированные URL JS/CSS/ru.json (?v=1.1.0), чтобы часовой кэш статики прежнего клиента не смешивал старый код и новые поля. При следующих релизах увеличивайте asset version.

## v1.5 — поделиться и обратная связь

Подробно — `15-utilities.md`.

| Метод и путь | Права | Ответ |
|---|---|---|
| GET/POST/DELETE /matches/{uuid}/share | участник; POST только для завершённого матча | 201 token / 200; 409 share_unavailable |
| GET /shared/{token} | без входа, 120/15 мин/IP | итог; 404 share_not_found |
| POST /feedback | сессия; message 1–2000, page ≤ 200; 10/15 мин/IP | 201 |

## v1.4 — игровые часы

Подробно — `14-game-clock.md`. Команды часов не используют `version` и не увеличивают её; SSE присылает отдельное событие `clock`.

| Метод и путь | Права | Ответ |
|---|---|---|
| GET /matches/{uuid}/clock | участник | состояние часов |
| POST /matches/{uuid}/clock | участник, active; request_id, action configure/start/pause/switch, mode?, limit_minutes?, slot? | 200 ok, changed, clock; 409 clock_* |
| GET /matches/{uuid}/events | участник | события `revision` (version) и `clock` (seq) |

## v1.3 — инициатива и подсчёт итога

Подробно — `13-turning-points.md`.

| Метод и путь | Права | Ответ |
|---|---|---|
| POST /matches/{uuid}/initiative | участник, active; request_id, version, turning_point ≤ current_turn, slot | 200; 409 initiative_closed |
| GET /matches/{uuid}/preview | участник, active, последний TP | 200 scoring_mode, ready, players (основная операция соперника скрыта); 409 preview_closed |
| GET /matches/{uuid} | + initiatives[] | |

## v1.2 — быстрый старт и hot-seat

Подробно — `12-quickstart-hotseat.md`.

| Метод и путь | Права | Ответ |
|---|---|---|
| POST /matches | сессия; request_id, kind friend/hotseat, edition, mission_id?, guest_name? | 201 id |
| POST /matches/{uuid}/invite | создатель friend-матча в setup, слот 2 пуст; request_id | 201 code, expires_at |
| POST /invites/{code}/join | сессия; request_id; 20/15 мин/IP | 200 match_id; 404/409/410 |
| PUT /matches/{uuid}/player-setup | участник в setup; request_id, version, slot, roster, operative_count, primary_op?, tac_op_id?, aspect_counts | 200 |
| scores / kills / primary / reveal-tac | необязательный slot: чужой слот только у создателя hot-seat для гостя | 403 slot_forbidden |
| actions | action=cancel (создатель, setup); hot-seat finish → unconfirmed | 200 status |

## v1.6 — английский интерфейс

`GET /api/shared/{token}` дополнительно возвращает `mission_code`, `killzone_code` и `players[].team_code` (коды справочника) — клиент показывает по ним английские названия. Остальные эндпоинты не менялись; сообщения об ошибках по-прежнему передаются кодом в `detail` и переводятся на клиенте (`web/i18n/{ru,en}.json → errors`). Подробно — `16-i18n.md`.

## v1.7 — справочник команд

| Метод и путь | Права | Ответ |
|---|---|---|
| GET /teams | сессия | `teams[]`: slug, name, catalog_id, archetypes, operatives, imported_at; `import`: последняя загрузка (sources с коммитами) или null |
| GET /teams/{slug} | сессия | slug, name, catalog_id, data (operatives, faction_rules, strategy_ploys, firefight_ploys, equipment, selection), sources, imported_at; `ETag`, `If-None-Match` → 304; 404 `team_not_found` |

Изменяющих эндпоинтов нет: данные загружает администратор (`scripts/import-teams.sh`). Подробно — `17-teams-and-design.md`.

## v1.8 — ростеры

| Метод и путь | Права | Ответ |
|---|---|---|
| GET /teams/{slug}/roster-schema | сессия | `{slug, name, catalog_id, hash, schema}`; `ETag` = `roster_hash`, `If-None-Match` → 304; 404 `team_not_found` / `roster_schema_missing` |
| GET /rosters | сессия, свои | `rosters[]` (id, team_slug, team_name, catalog_id, name, version, updated_at, valid, operatives, errors, stale), `teams[]` со схемой, `limit` |
| POST /rosters | сессия; request_id, team_slug, name, data? | 201 ростер (повтор request_id — тот же); 409 `roster_limit`; 422 `roster_schema_missing`, `roster_format`, `roster_too_large`, `roster_too_deep` и др. `roster_*` |
| GET /rosters/{id} | владелец | ростер с `data`, `summary`, `version`, `stale`; чужой или нет — 404 `roster_not_found` |
| PUT /rosters/{id} | владелец; version, name, data | 200 новая версия и `summary`; 409 `version_conflict` |
| DELETE /rosters/{id} | владелец; тело `{}` | 200 `{ok: true}`; ссылки из матчей обнуляются |
| GET /rosters/{id}/export?format=text\|json\|ros\|rosz | владелец | файл (`.txt`, `.json`, BattleScribe `.ros`/`.rosz`); кириллица в имени — `filename*=UTF-8''…` |

`PUT /matches/{uuid}/setup` и `PUT /matches/{uuid}/player-setup` принимают необязательный `roster_id` (null — отвязать): ростер должен принадлежать этому игроку и команде слота, иначе 422 `roster_not_found` / `roster_team_mismatch`. `GET /teams/{slug}` дополнительно отдаёт все варианты правил фракции (`faction_rules[].options`). Тело запросов к `/api/rosters*` — до 256 КБ, к остальным — 32 КБ. Подробно — `18-rosters-and-board.md`.

## v1.9 — трекер, отмена, турниры, администрирование

Все изменяющие запросы — с `request_id` и CSRF, как раньше.

| Метод и путь | Права | Ответ |
|---|---|---|
| POST /matches/{id}/operatives | участник; `action` = populate \| add \| wounds \| order \| activate \| remove, `slot`, `operative_id`, `delta`, `order`, `activated`, `card`, `name`, `wounds_max` | populate/add — `{ok, ids}`, remove — `{ok}`, остальные — `{ok, changed}`; 409 `tracker_closed`, `tracker_not_empty`; 404 `operative_not_found`; 403 — чужой оперативник; 422 `roster_required`, `tracker_full`, `card_unknown`, `operative_name_required`, `operative_required`, `delta_required`, `order_required`, `activated_required` |
| POST /matches/{id}/undo | участник; `audit_id` из `undo` в ответе матча | `{ok, action}`; 409 `undo_closed` (матч не идёт), `undo_conflict` |
| GET /matches/{id}/players/{slot}/roster | участник | ростер игрока как в матче (оперативники с выбранным оружием); чужой до старта — 403 `roster_hidden` |
| GET /rosters/{id}/sheet | владелец | оперативники для печати (имя, характеристики, оружие) |
| POST /rosters/import | сессия; `filename`, `data_b64`, `name?`, `team_slug?` | 201 `{id, team_slug, name, imported, skipped[], forces, valid, operatives}`; 413 `import_too_large`; 422 `import_invalid`, `import_not_roster`, `import_team_unknown`, `roster_schema_missing`, `roster_too_large`; 409 `roster_limit` |
| GET /ratings | сессия | `{players:[{public_id, display_name, rating, rank, me, games, wins, draws, losses}], games, start, k}` |
| GET /tournaments | сессия | свои и те, где вы участник |
| POST /tournaments | сессия; `name`, `format` = swiss \| league, `rounds?`, `players[]` (`public_id` друга или `name` гостя) | 201 `{id}`; 422 `tournament_friend_required`, `tournament_duplicate_player`, `tournament_rounds`; 429 `too_many_tournaments` |
| GET /tournaments/{id} | организатор или участник | турнир, участники, пары, таблица |
| DELETE /tournaments/{id} | организатор | `{ok}` |
| POST /tournaments/{id}/actions | организатор; `version`, `action` = start \| next_round \| finish | `{ok}`; 403 `tournament_owner_only`; 409 `tournament_state`, `tournament_round_open`, `tournament_too_small`, `version_conflict` |
| POST /tournaments/{id}/pairings/{pid}/result | организатор или игрок пары; `vp1`, `vp2` (оба null — очистить) | `{ok}`; 403 `tournament_owner_only`; 409 `tournament_state`, `pairing_bye`; 422 `result_incomplete` |
| POST /tournaments/{id}/players/{plid}/drop | организатор; `dropped` | `{ok}` |
| POST /tournaments/{id}/pairings/{pid}/match | игрок пары | 201 `{id}` матча (с другом — дружеский, с гостем — hot-seat); 403 `pairing_not_player`; 409 `tournament_state`, `pairing_closed`, `pairing_has_match` |
| GET /admin/overview | администратор | `{version, migrations, counts, matches, team_import}`; остальным 403 `admin_only` |
| GET /admin/feedback?status=open\|all | администратор | `{items, total}` |
| POST /admin/feedback/{id} | администратор; `handled` | `{id, handled_at}` |
| GET /admin/users?q= | администратор | `{items, total}` |

Изменения существующих ответов: `GET /matches/{uuid}` — `operatives[]`, `tracker_seq`, `undo` (что отменит кнопка); `GET /stats` — `breakdown.roster_id`, `clock`; `GET /auth/me` — `is_admin`; `GET /health` — `{status, version, migrations}` (503 `migration_required`, пока применены не все); SSE `/matches/{uuid}/events` — событие `tracker`. Тело `/api/rosters/import` — до 1 МБ, прочих `/api/rosters*` — 256 КБ, остальных — 32 КБ. `scripts/feedback.sh` удалён: `POST /feedback` прежний, читает отзывы `#admin`. Подробно — `19-v1.9.md`.

## v1.10 — офлайн-табло, вечера, сезоны, ТВ, схема килзоны, push

Все изменяющие запросы — с `request_id` и CSRF, как раньше. Полная таблица путей, прав и кодов ошибок — `20-v1.10.md`, раздел «API».

- **Сброс пароля:** `POST /admin/users/{public_id}/password-reset` (администратор; одноразовый код, хранится только хэш, срок `RESET_TTL_MINUTES`), `POST /auth/password-reset` (без входа: `identity`, `code`, `password`; 400 `reset_code_invalid`, 5 попыток на код, 10 запросов за 15 минут с IP). После сброса прочие сессии завершаются.
- **Игрок:** `GET, PATCH /profile/extra` (девиз, любимая команда, скрытый профиль), `POST, DELETE /profile/avatar` (PNG/JPEG/WebP до 192 КБ, стороны 16–512: браузер обрезает до 256×256 и перекодирует без EXIF, сервер сверяет сигнатуру с типом и размеры), `GET /users/{public_id}/avatar`, `GET /players/{public_id}` (страница игрока).
- **Сезоны и достижения:** `GET /seasons`, `GET /seasons/{id}/ratings`, `GET /achievements`; администратор — `/admin/seasons`, `/admin/achievements` (+ `POST …/recompute`).
- **Игровые вечера:** `GET, POST /nights`, `GET, PUT /nights/{id}`, `POST /nights/{id}/rsvp`, `POST /nights/{id}/pairs`, `POST /nights/{id}/pairs/{pid}/match`, `GET /nights/{id}/calendar.ics`; личная лента календаря — `GET, POST, DELETE /calendar/token` и `GET /calendar/{token}.ics` (по ключу, без сессии).
- **ТВ:** `GET, POST /admin/tv`, `DELETE /admin/tv/{id}`; экран — `GET /tv/{key}` и аватары `GET /tv/{key}/avatar/{public_id}` (по ключу, без сессии, только чтение).
- **Схема килзоны:** `GET, POST /boards`, `GET, PATCH, DELETE /boards/{id}`, `PUT, DELETE /boards/{id}/frames/{n}` (кадр на каждый поворотный момент, `version` для конфликтов).
- **Push:** `GET /push/config`, `POST /push/subscriptions`, `/push/unsubscribe`, `/push/test`; 409 `push_disabled`, пока оператор не включил push.
- **События:** `GET /events?match=&board=` — один SSE-поток пользователя (`notify`, `revision`, `clock`, `tracker`, `board`); прежний `/matches/{uuid}/events` сохранён.
- **Сервис-воркер:** `GET /sw.js` (`Cache-Control: no-cache`, `Service-Worker-Allowed: /`).

Изменения существующих ответов: `POST /matches/{id}/clock` принимает `at` — время нажатия, сделанного без сети (сервер принимает его в пределах окна очереди и не раньше предыдущего события часов); `GET /auth/me` и профиль — `avatar`; новые виды уведомлений (вечера, достижения). `APP_ORIGIN` может содержать несколько origin через запятую (IP, домен, имя Tailscale). Спецификация — `docs/openapi.json`.

## v1.11 — справочник правил с поиском

- `GET /reference/search?q=&kind=&team=&lang=&limit=&offset=` (сессия): один поиск по общим правилам, каталогу, последовательности игры и данным команд. `kind` — rules | ops | teams | operatives | ploys | equipment, `team` — slug команды, `lang` — ru | en (английские тексты каталога), `limit` 1–50 (20), `offset` до 500. Ответ `{q, terms, total, offset, results[]}`; у записи — `id`, `kind` (weapon_rule, phase, rule, sequence, mission, tac_op, team, operative, faction_rule, ploy, equipment), `title`, `subtitle` (название на другом языке, ключевые слова, архетипы, фаза), `code`, `verification`, `source_url`; у записей команд — `team {slug, name, label}`, `link` (`#teams/<slug>/<вкладка>/<якорь>`), `snippet`; у остальных — `text`, `text_ru`. 422 `search_query_short` — запрос короче 2 символов без фильтров. Ответы не кешируются сервис-воркером.
- `GET /reference/library` (сессия): общие правила для просмотра и офлайн-поиска (`code`, `kind`, `name`, `name_ru`, `aliases`, `text_en`, `text_ru`, `details`, `verification`, `source`, `imported_at`) и `status` («актуально»: последний импорт правил с релизом oracle, импорт команд, версия каталога, последнее обновление и последняя успешная проверка). `ETag`, 304 при `If-None-Match`, `Cache-Control: private, max-age=0, must-revalidate`.
- `GET /admin/overview` — новое поле `reference {status, updates[]}` (10 последних записей журнала `update-reference.sh` с кратким отчётом).

Панель «Справка» в матче вызывает `/reference/search` (`limit=8`); `GET /reference/rules` сохранён. Подробно — `21-v1.11.md`, `docs/openapi.json`.

## v1.12 — основные правила, готовый террейн схем

- `GET /reference/core-rules` (сессия): документ «Основные правила» целиком (~120 КБ) — `{format, title, source, version, chapters[]}`; глава — `id`, `title`, `ru`, `intro?`, `sections[]`; раздел — `id`, `title`, `ru`, `page` (страница PDF книги), `blocks[]` (`h` с `id` якоря, `p`, `ul`/`ol`, `note` — заметка разработчиков, `ex` — пример или подпись схемы, `action` с `ap`/`eff`/`cond`, `ploy`, `card`, `stats`, `table`, `box`, `flow`; у изменённых после книги — `upd {book}` (прежняя формулировка) или `upd {added: true}`). `ETag: "core-<version>"` (хэш содержимого), 304 при `If-None-Match`, `Cache-Control: private, max-age=0, must-revalidate`, `Vary: Cookie`. Поиск идёт в браузере; сервис-воркер хранит последнюю копию.
- `POST /boards`: `layout` — id готового террейна (`""` — без террейна; поле не указано — у схемы матча раскладка по карте каталога (`2024-wahapedia-killzone-volkus-N` → `volkus-2025-N`), у свободной — без террейна) и `swap` (игрок 1 в другой зоне высадки). С террейном размер всегда 30″ × 22″, `width`/`height` не учитываются; оперативники схемы матча встают в зоны высадки. 422 `layout_unknown`.
- `PATCH /boards/{id}`: `layout` (не указан — без изменений, `""` — убрать) и `swap`; у схемы матча оперативники кадра 0, которых не двигали, переходят на места новой расстановки (версия кадра 0 растёт), передвинутые остаются.
- `GET /boards` — новое поле `layout`; `GET /boards/{id}` и ответы `POST`/`PATCH` — `layout`, `swap`.

Подробно — `22-v1.12.md`, `docs/openapi.json`.

## v1.13 — сдача матча, локальные игроки, рейтинг клуба, число оперативников, подсказки терминов

- `POST /matches/{id}/actions`: `action=concede` — из `active`, на любом поворотном моменте, без проверок конца боя; у hot-seat — необязательный `slot` (кто сдаётся, по умолчанию свой слот). Матч с другом → `awaiting_confirmation` (`submitted_by` — сдавшийся, подтверждает или оспаривает соперник), hot-seat → `unconfirmed`. Итог — 10:0 в `player_totals`. `reopen` (после `dispute`) снимает сдачу. В `GET /matches/{id}` — `conceded_slot` (1, 2 или null).
- `PUT /matches/{id}/setup` и `PUT /matches/{id}/player-setup`: `operative_manual` (bool, по умолчанию false). Число оперативников решает сервер: прикреплённый ростер (`summary.operatives`) → состав команды → `operative_count` из запроса; с `operative_manual: true` и числом в запросе — это число. Источник — `players[].operative_source` (`roster`/`team`/`manual`). При `action=start` числа из ростера и команды пересчитываются.
- `POST /matches` (hot-seat) и `POST /quick-matches`: `local` (bool) — `guest_name` — локальный игрок: пробелы сжимаются, имя ищется без учёта регистра и «ё» или создаётся; в матче — `players[].local_player_id`. 422 `local_player_name_required`, 429 `too_many_local_players` (больше 300 записей от одного аккаунта).
- `GET /local-players` (сессия): `{items:[{id, name, matches}]}` — общий список клуба по имени (до 2000).
- `GET /admin/local-players`: `{items:[{id, name, created_at, created_by_name, created_by_id, matches, last_played}]}`; `DELETE /admin/local-players/{id}` (тело `{}`) → `{ok}`, 404 `local_player_not_found`; матчи остаются, `local_player_id` становится NULL.
- `GET /ratings?scope=friends|all` (по умолчанию `friends` — как раньше); в ответе `scope`. `all` — рейтинг клуба: подтверждённые матчи между зарегистрированными игроками и `unconfirmed` матчи hot-seat и быстрые записи создателя против локального игрока; строки с `local` (у локальных `public_id` null), скрытые профили не показываются (кроме себя), до 500 строк.
- `GET /teams`: у команд `team_size` (число оперативников состава или null) и `team_size_varies` (состав бывает другим).
- `GET /reference/terms` (сессия): `{version, terms[]}` — 67 терминов с подсказками: `id`, `kind` (`term`, `terrain`, `action`, `weapon`), `name`, `ru`, `sec` и `anchor` (раздел основных правил), `where`/`where_ru`, `def[]` — официальный текст (строки или списки), `alias[]` (`re` — регулярное выражение JavaScript, `t` — в тексте правил: `s` с учётом регистра, `i` без, null — нет; `w` — в правилах оружия датакарт; `n` — длина для порядка «длинные первыми»). `ETag: "terms-<version>"`, 304 при `If-None-Match`, `Cache-Control: private, max-age=0, must-revalidate`, `Vary: Cookie`; сервис-воркер хранит копию.
- `GET /reference/core-rules`: `format: 2` — у разделов нет `page`, у блоков нет `upd`; `source {book, updates, text}`; добавлен `terms[]` (как в `/reference/terms`).

Подробно — `23-v1.13.md`, `docs/openapi.json`.

## v1.14 — сводка меню, снаряжение, CP за поворот, ploys, правила оперативников, журнал ошибок браузера

- `GET /nav-summary` (сессия): только числа для групп меню — `{history:{games, to_confirm, live}, stats:{games, win_rate}, friends:{friends, challenges, requests}, nights:{next, unanswered}, tournaments:{active}, rosters:{count, invalid}, maps:{count}}`. `to_confirm` — матчи `awaiting_confirmation`, отправленные соперником; `challenges` — входящие ожидающие вызовы; `unanswered` — запланированные вечера без ответа игрока. Клиент запрашивает её не чаще раза в 30 с и при новом уведомлении.
- `GET /matches/{id}/equipment?slot=` (участник; свой слот, у hot-seat — оба): `{slot, team_id, max: 4, edition, options[], selected[], suggested[]}`; вариант — `{key, name, group: universal|faction, rules[{name, type: equipment|action|ability, text}], weapons[]}` (профили оружия — как у датакарт). `suggested` — ключи снаряжения, выбранного в прикреплённом ростере. 403 `slot_forbidden`.
- `PUT /matches/{id}/equipment` (участник): `{request_id, version, slot?, keys[]}` — до 4 ключей без повторов, только в `setup` и в Kill Team 2024: `{ok, count}`; 409 `equipment_closed`, 422 `equipment_limit` / `equipment_repeat` / `equipment_unknown` / `equipment_edition` / `team_required`. Аудит записывает только число вариантов.
- `GET /matches/{id}`: у игроков `equipment` (своё всегда, чужое — после старта; до него `[]`) и `equipment_count`; `cp_grants[{turning_point, gains}]`; `ploys[{id, player_id, slot, turning_point, kind, name, cost, created_at}]`.
- `POST /matches/{id}/actions` `action=start` (2024): снаряжение сверяется с текущим справочником и раскрывается (аудит `equipment_reveal` с названиями), затем каждому игроку 2CP (аудит `cp_start`, `match_cp_grants` с `turning_point` 0).
- `POST /matches/{id}/cp` (участник): `{request_id, version, turning_point}` — только текущий поворотный момент: TP1 — +1 обоим, с TP2 — игроку с инициативой +1, другому +2: `{ok, gains}`; 409 `cp_closed` (матч не идёт или не тот TP) / `cp_granted` (уже начислено) / `initiative_required`, 422 `cp_edition`. Смена инициативы после начисления (`POST /matches/{id}/initiative`) переносит лишний CP (в аудите `cp_change`).
- `POST /matches/{id}/ploys` (участник): `{request_id, version, slot?, kind: strategy|firefight, name, cost (0–3, по умолчанию 1), repeat}` — ploy команды игрока (`strategy_ploys`/`firefight_ploys` справочника) или `Command Re-roll` (только `firefight`): `{ok, id, cp}`; 409 `ploy_closed` / `ploy_repeat` (уже использован в этом TP — повтор только с `repeat: true`; Command Re-roll не ограничен), 422 `ploy_unknown` / `cp_insufficient`.
- `POST /matches/{id}/undo`: отменяет и `cp_grant` (CP и запись начисления), и `ploy` (CP и запись протокола).
- `GET /stats/ploys` (сессия; фильтры как у `/stats`): `[{name, kind, uses, games, cp}]`, до 50, по завершённым матчам игрока.
- `GET /rosters/{id}/sheet` и ростер игрока в матче (`GET /matches/{id}/players/{slot}/roster`): у оперативников `abilities[{name, type, text}]` (`type` пустой у Abilities), `actions[{name, text}]` (Unique Actions), `keywords[]`; `extras[]` — правила остальных выборов ростера (снаряжение и т. п.). Правила — профили модели и выбранных опций без повторов, без профилей в схеме — правила датакарты.
- `POST /client-errors` (без сессии, лимит 30 за 15 минут с адреса, тело до 16 КБ — иначе 413): `{kind: error|rejection, message, source, stack, page, version}` → 202 `{ok}`; адреса без параметров и фрагментов, длинные токены вырезаются; повтор в тот же день увеличивает счётчик. 422 `message_required`, 429 `rate_limited`.
- `GET /admin/client-errors?limit=&offset=` (администратор): `{items[{id, day, kind, message, source, stack, page, version, agent, count, first_at, last_at, login, public_id}], total{n, events}, keep_days}`; `POST /admin/client-errors/clear` `{request_id}` → `{ok, deleted}`; в `GET /admin/overview` — `client_errors_week`.

Подробно — `24-v1.14.md`, `docs/openapi.json`.

## v1.15: запись результата с аккаунтом

`POST /quick-matches` с `opponent_public_id` создаёт запись для двух аккаунтов со статусом `awaiting_confirmation`, `kind=friend` и `recorded_result=true`. Получатель подтверждает или оспаривает её через `/matches/{id}/actions`; автор не может подтвердить свой результат, но может отменить ожидающую или оспоренную запись. При споре записывают новый результат вместо `reopen`. Самому себе или при блокировке в любую сторону отправить запись нельзя. Без ID сохраняется прежний гостевой сценарий. Успешное подтверждение включает запись в общие статистику, рейтинг и достижения. Полные схемы — `openapi.json`.
