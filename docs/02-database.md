# 2. База данных

Схема: неизменённые 001/002 и новые `003_catalog_and_ops.sql`, `004_verified_catalog.sql`. `db/legacy-seed.json` обеспечивает побайтно совместимый bootstrap неизменённой 002; текущий снимок — `db/seed.json`, самодостаточный SQL данных — 004. Мигратор — `db/migrate.sh`.

## ER / связи

```text
users 1 ── N sessions
users N ── N users         friendships (одна неупорядоченная пара), blocks (направленные)
users 1 ── N challenges   sender / recipient
challenges 1 ── 0..1 matches
users 1 ── N guest_opponents
users 1 ── N matches      created_by
matches 1 ── 2 match_players
users 1 ── N match_players (nullable после удаления)
guest_opponents 1 ── N match_players (nullable после удаления гостя)
catalogs 1 ── N matches / match_players / turning_point_scores
match_players 1 ── N turning_point_scores (поворот × источник)
match_players 1 ── N turning_point_states (поворот: CP, заметка)
matches 1 ── N match_audit
users 1 ── N notifications / operations
```

`users.id` — внутренний bigint identity, `public_id` — независимый криптографически случайный 8-символьный ID из алфавита без неоднозначных символов (40 бит). Коллизия не создаёт дубликат: UNIQUE отклоняет регистрацию, пользователь может повторить её. Публичного перебора всех пользователей нет.

Индексы: уникальная пара друзей; входящие вызовы; игрок+матч; дата+UUID матча; журнал+ID; срок сессий; уведомления пользователя. Составной PK очков защищает от двойных строк одного источника. `source_id` проверяется API на kind/edition; FK защищают существование. Не следует писать игровые данные напрямую из сторонних приложений: межтабличные проверки выполняет сервис.

## Инварианты и транзакции

- Каждый матч создаётся с двумя местами игроков одной транзакцией.
- Оба участника могут менять общую подготовку, но состав редактируется только у себя; после старта параметры фиксированы.
- Каждая запись VP/CP блокирует строку матча `FOR UPDATE`, проверяет членство и version.
- Версия увеличивается вместе с записью и аудитом. Ошибка откатывает всё.
- UUID request_id + пользователь + hash payload обеспечивают повторяемость игровых команд; иной payload с тем же ключом даёт 409.
- Завершение и подтверждение — атомарные переходы, заявитель не подтверждает сам себя.
- Аудит хранит до/после VP/CP, настройки и тип изменения заметок, но не дублирует текст заметок/составов.
- Удаление аккаунта удаляет сессии/социальные данные/собственные гостевые матчи, а в общих матчах стирает имя, состав и личные заметки; итоговый результат сохраняется у соперника.
- Удалённый участник не сможет подтвердить ожидающий матч; такой матч не попадает в статистику.

## Статистика

`player_results` вычисляет VP через SUM из первичных очков. Один подтверждённый общий матч даёт две перспективы результата. Гостевая запись — одну, только для владельца. Никаких хранимых дублирующих итогов VP или побед.

`/api/stats` применяет фильтры, затем SQL FILTER/AVG/GROUP BY; серии — оконные функции. Win rate = победы / все игры × 100; ничья не половина победы. Личные встречи включают только зарегистрированных соперников. Все разбивки считают игры/победы/ничьи/поражения/среднюю разницу VP. Серии вычисляются по выбранной выборке, сортировка `(played_at, UUID)` детерминированная. Месяцы и границы фильтра дат — Europe/Moscow.

## Миграции и справочники

Файлы SQL исполняются по имени, только один раз, с advisory lock и транзакцией на файл. Не меняйте уже применённый файл: добавляйте следующий свободный номер, начиная с `005_*.sql`. SQL и `\copy` поддерживаются через psql. Миграции на первом старте выполняются entrypoint PostgreSQL; после обновления — `scripts/migrate.sh` при остановленном API.

Изменение seed.json само по себе не меняет существующую БД: `002_seed.sql` уже отмечена применённой. Для обновления используйте tools/catalog-import и новую самодостаточную миграцию UPSERT (см. docs/09-catalog-import.md). Существующие записи не удаляйте — выключайте `active=false`, чтобы сохранять историю. Изменение метки отображается и в старых матчах; для версионированных правил создавайте новые code/ID.

БД-владелец используется только init/миграциями/бэкапом. Сервис подключается как `killstass_app`: NOSUPERUSER по умолчанию, без CREATE в public, DML на таблицах, только INSERT/SELECT на аудите, SELECT на версиях схемы. Сервис не получает пароль владельца. Разделение прав не заменяет защиту API: прямой доступ к роли приложения даёт доступ ко всем игровым данным; поэтому порт PostgreSQL не опубликован.


## Расширения v1.1

```text
catalogs(team) config.archetypes / conditional_archetypes
catalogs(tac_op) 1 ── N match_players.tac_op_id / turning_point_scores.tac_op_id
match_players 1 ── N operative_kills (поворот × дельта текущих выведенных врагов)
game_sequence (edition × phase_order × step_order, стабильный code)
matches.rules_snapshot → источники, thresholds, caps Crit/Tac на момент старта
player_totals VIEW → player_results VIEW → существующие SQL-агрегаты
```

`catalogs` получает source, source_url, retrieved_at (UTC), rules_version, SHA-256 raw-content, label_en и verification. Новые kind: pack/archetype/tac_op/rule. Game Sequence — отдельная таблица с такими же метаданными. runtime-роль только читает оба справочника; DDL и изменение справочников доступны владельцу через миграции.

У всех существующих матчей scoring_mode='legacy'; их итог ровно SUM прежних VP, без новых бонусов. Новый реальный setup с Approved Ops переводится в approved2025. До старта каждый игрок сохраняет одну Tac Op, свой состав, количество засчитываемых для Kill Op оперативников и предварительную primary_op. Поля primary_committed/tac_revealed определяют видимость; в TP1 основная цель фиксируется отдельной идемпотентной командой. Снимок API убирает чужую нераскрытую цель и все секретные tacs из rules_snapshot; live-matches не отдаёт rules_snapshot вообще; аудит фиксации не содержит выбранного направления.

На старте числовые ограничения и выбранные Tac Op фиксируются как неизменяемые параметры rules_snapshot. Это не дублирующие результаты, а версия правил. Импорт не меняет итог уже начатых/подтверждённых матчей. Сам счёт не кэшируется и не хранится в matches.

`player_totals`: Crit/Tac = суммы первичных VP по замороженным источникам; grade = число достигнутых порогов исходного количества противников (5–14) по SUM оперативных дельт. Kill VP = grade + 1 только в конце боя, если grade выше вражеского. Затем добавляется ceil(VP выбранного направления / 2). Сравнение выполняется по grade, не по числу убийств и не по Kill VP с бонусом. Возвращение врага корректируется отрицательной дельтой, с проверкой промежуточных сумм. CP остаётся ручным остатком на повороте.

В конце четвёртого поворота VP за условия «end of battle» вносятся в TP4 соответствующего направления, после чего finish закрывает ввод и одновременно раскрывает обе основные цели. Dispute исключает матч из статистики; reopen снова открывает ввод, не изменяя выбранные цели/правила. Подтверждение сохраняет прежний атомарный жизненный цикл. Перестановка номеров поворотов — просмотр/ручная правка, а не полноценный rules-engine.

## Эксплуатационный default v1.1.1

После создания runtime-роли db/migrate.sh задаёт `ALTER ROLE killstass_app IN DATABASE <current_database> SET jit = off` через SQL format(%I). Это не изменение схемы или итогов. Defaults действуют для новых соединений; update/restore перезапускают API. На fresh init роль появляется после файлов миграций, поэтому отдельный 005 с ALTER ROLE был бы неверным порядком. При restore настройка/права применяются повторно. Глобальный jit и owner-сессии не меняются.

## v1.2 — 005_invites_hotseat.sql

- `matches.kind`: friend, guest, **hotseat**.
- `match_invites`: одноразовые коды присоединения к пустому слоту 2 (TTL, used_by/used_at, не более одного открытого кода на матч).
- `player_totals` начисляет бонусы конца боя и для `unconfirmed`; `player_results` учитывает hot-seat только у владельца.
- Подробно — `12-quickstart-hotseat.md`.

## v1.3 — 006_initiative.sql

- `turning_point_initiative`: кто получил инициативу в каждом повороте (PK match_id+turning_point, slot 1/2, decided_by, created_at). TP1 по умолчанию — `matches.initiative` из настройки.
- Изменения — через `POST /matches/{id}/initiative` с аудитом `initiative`. Подробно — `13-turning-points.md`.

## v1.4 — 007_match_clock.sql

- `match_clock_events`: append-only журнал часов (configure/start/pause/switch, режим, лимит, slot, actor_id, `server_ts = clock_timestamp()`). Состояние вычисляется из событий (`domain.clock_state`), не хранится.
- Не меняет `matches.version`; при `finish` запущенные часы получают событие `pause`. Подробно — `14-game-clock.md`.

## v1.5 — 008_share_feedback.sql

- `match_shares`: одна ссылка для просмотра на матч, хранится только SHA-256 токена; каскад при удалении матча.
- `feedback`: сообщения администратору (каскад при удалении аккаунта, `handled_at` ставит `scripts/feedback.sh done ID`; с v1.9 — кнопка «Обработано» на странице `#admin`). Подробно — `15-utilities.md`.

## v1.7 — 009_team_data.sql

- `team_data`: справочник команд (slug PK, name, `catalog_id` → catalogs ON DELETE SET NULL, `data` jsonb, `sources` jsonb с репозиториями и коммитами, `content_hash` SHA-256 для ETag, `active`). Не связан со счётом матчей.
- `team_data_imports`: журнал загрузок (время сборки пакета, источники, число команд/оперативников, предупреждения сверки).
- Права: `killstass_app` — только SELECT (как `catalogs`); пишет владелец БД через `scripts/import-teams.sh`. Подробно — `17-teams-and-design.md`.

## v1.8 — 010_rosters.sql

- `team_data`: новые колонки `roster_schema jsonb` (схема конструктора, собранная из BSData при импорте) и `roster_hash` (SHA-256, ETag схемы). Пишет только владелец БД через `scripts/import-teams.sh`.
- `rosters`: ростеры пользователей (`id uuid`, `user_id` → users ON DELETE CASCADE, `team_slug`, `name` 1–80, `data jsonb` ≤ 256 КБ, `schema_hash`, `summary jsonb` с итогом проверки, `version` для оптимистичной блокировки, `created_at`, `updated_at`); индекс `(user_id, updated_at DESC)`. Роль приложения — SELECT/INSERT/UPDATE/DELETE; лимит 100 ростеров на аккаунт проверяет API.
- `match_players.roster_id` → rosters ON DELETE SET NULL: какой ростер игрок использовал в матче (удаление ростера матч не трогает). Подробно — `18-rosters-and-board.md`.

## v1.9 — 011_tracker_tournaments.sql

- `users.is_admin boolean NOT NULL DEFAULT false` — доступ к `#admin`. Меняет только владелец БД (`scripts/admin.sh`): `db/migrate.sh` с v1.9 забирает у `killstass_app` `INSERT/UPDATE` на всю таблицу `users` и выдаёт обратно только `INSERT(public_id, login, email, display_name, password_hash)` и `UPDATE(display_name, password_hash)`.
- `match_operatives`: трекер (`id`, `match_id` → matches и `player_id` → match_players, оба ON DELETE CASCADE; `position` 1–40, уникальна у игрока; `name` 1–80, `card` — имя датакарты; `stats`/`weapons` jsonb, вместе ≤ 16 КБ; `wounds_max` 1–99, `wounds` 0…`wounds_max`; `order_token` engage/conceal; `activated_tp`, `incapacitated_tp` 1–12). Инвариант: `wounds = 0` ⇔ `incapacitated_tp IS NOT NULL`; поворот вывода из строя попадает в `operative_kills` соперника (Approved Ops 2025, TP 1–4). Частые изменения не трогают `matches.version`; номер для SSE — последний `match_audit.id` действий трекера.
- `tournaments` (`owner_id` → users ON DELETE CASCADE, `name` 1–80, `format` swiss/league, `rounds` 1–30, `status` draft/active/finished, `current_round` 0–30, `version` для оптимистичной блокировки); `tournament_players` (`user_id` → users ON DELETE SET NULL или только `name` гостя 1–64, `seed` уникален в турнире, `dropped`; один аккаунт — один раз); `tournament_pairings` (`round`, `table_no` уникальны в турнире; `player2_id IS NULL` — bye; `match_id` UNIQUE → matches ON DELETE SET NULL; ручные `vp1`/`vp2` 0–999 — оба или ни одного, `reported_by`).
- Роль приложения — SELECT/INSERT/UPDATE/DELETE на новые таблицы (общий GRANT мигратора). Действия трекера и отмены пишутся в `match_audit` (`operative`, `operatives_populate`, `undo`). Подробно — `19-v1.9.md`.

## v1.10 — 012_v110.sql

- `password_resets`: одноразовые коды сброса пароля (`user_id` → users ON DELETE CASCADE, `code_hash` — SHA-256 кода вместе с ID аккаунта, `created_by` — администратор или NULL для `scripts/admin.sh password`, `expires_at`, `used_at`, `attempts` — 5 неверных попыток гасят код). Частичный уникальный индекс: не больше одного неиспользованного кода на аккаунт (новый код заменяет старый).
- `user_profiles` (девиз до 140, `favorite_team_id` → catalogs ON DELETE SET NULL, `hidden`) и `avatars` (PNG/JPEG/WebP 64 Б–192 КБ, `sha256` — версия для кеша) — по одной строке на аккаунт, каскад при удалении.
- `seasons` (название, `starts_on`–`ends_on`, `k_factor` 4–64, `start_rating` 100–3000; пересечение дат проверяет API) — рейтинг сезона не хранится, а считается по `player_results` подтверждённых дружеских матчей. `achievements` (код, названия и описания RU/EN, значок, `rule` из девяти правил, `threshold` 1–1000, `season_id` → seasons ON DELETE RESTRICT, `active`, `builtin`, `position`; три встроенных — `first_win`, `matches_10`, `comeback`) и `user_achievements` (PK пользователь + достижение, `earned_at`, `match_id` → matches ON DELETE SET NULL).
- `game_nights` (`organizer_id` → users ON DELETE SET NULL, название, `starts_at` < `ends_at`, место, заметки, `capacity` 2–64, `status` planned/cancelled, `pairs_published_at`, `version`), `game_night_rsvps` (PK вечер + игрок, `answer` yes/maybe/no, команда, комментарий), `game_night_pairs` (`table_no` уникален в вечере, `b_id IS NULL` — bye, `match_id` → matches ON DELETE SET NULL), `calendar_tokens` (одна подписка на аккаунт, только хэш ключа).
- `tv_screens` (подпись, ключ 24–64 символа `[A-Za-z0-9_-]`, `tournament_id` → tournaments ON DELETE SET NULL — NULL: все активные, `last_seen_at`).
- `boards` (`owner_id` или `match_id` UNIQUE — у матча одна схема, каскад при удалении матча; размер 6–60″, `seq` — номер изменения для события `board`) и `board_frames` (PK схема + кадр 0–12, `state` jsonb — жетоны в дюймах, заметка до 500, `version` для оптимистичной блокировки, `updated_by`).
- `push_subscriptions` (endpoint `https://` UNIQUE, ключи `p256dh`/`auth`, язык сообщений, `last_ok_at`, `failures` — после 50 ошибок подписка удаляется, 404/410 — сразу), `push_outbox` (очередь для `pushworker`: пользователь, вид уведомления, ID объекта), `app_settings` (ключ → jsonb; пара ключей VAPID).
- Существующие таблицы не менялись. Роль приложения получает SELECT/INSERT/UPDATE/DELETE на новые таблицы общим GRANT мигратора. Подробно — `20-v1.10.md`.

## v1.11 — 013_v111.sql

- Sweep & Clear: UPSERT `2024-wahapedia-tac-op-sweep-clear` — `active=true`, `verification=verified`, `per_turn_caps` [0,2,2,2], `max_per_battle` 6, ссылка на errata GW, новый `content_hash` (SQL из `tools/catalog-import` по `db/seed.json`). Сыгранные матчи хранят свой `rules_snapshot`.
- `CREATE EXTENSION IF NOT EXISTS pg_trgm`; функции `ks_fold` (нижний регистр, «ё» → «е», пробелы — не зависит от локали БД, совпадает с `api/library.fold`), `ks_arr` (не массив → `[]`), `ks_blocks` (текст блоков правил команды без lore). Все IMMUTABLE.
- `rule_entries`: общие правила справочника — `code` (`weapon-…`/`phase-…`) PK, `kind` weapon_rule/phase, `name`, `name_ru`, `aliases text[]` (другие русские названия для поиска), `text_en`, `text_ru` (редакторский пересказ), `details` (фазы: порядок, шаги, подсказки), `verification` bsdata/unverified, `source` (репозиторий, тег, коммит, путь, SHA-256 файла, дата генерации), `sort`, `active`, `content_hash`, `imported_at` (меняется только при изменении содержимого). `rule_imports` — история импортов (`built_at`, `sources`, счётчики, предупреждения).
- `reference_updates`: журнал `scripts/update-reference.sh` — `started_at`, `finished_at`, `action` update/rollback, `status` ok/unchanged/failed, `trigger` manual/timer, `backup` (файл дампа), `snapshot` (каталог пакетов), `sources`, `report` (сравнение, ростеры, предупреждения, ошибка); индекс по `finished_at DESC`.
- Материализованное представление `reference_search` — общий поисковый индекс: правила, записи каталога 2024 (миссии, Tac Ops, правила), последовательность игры, команды, оперативники, правила фракций, ploys, снаряжение; `title_f`/`sub_f`/`alias_f`/`text_f` (свёрнутый текст) и `doc` (`tsvector` `russian`: названия — вес A, текст — C). Индексы: уникальный `id`, GIN по `doc`, триграммы `title_f` и `text_f`. Обновляет владелец БД в конце каждой загрузки (`api/teamdata.REFRESH_SQL`).
- Роль приложения — только SELECT на новые таблицы и представление (`db/migrate.sh`); пишут их скрипты оператора от владельца. Существующие таблицы не менялись. Подробно — `21-v1.11.md`.

## v1.12 — 014_v112.sql

- `boards.layout text` — готовый террейн схемы: id раскладки из `web/killzones.js` (`volkus-2025-1`…`volkus-2025-6`, `volkus-example-3`), `CHECK (layout ~ '^[a-z0-9-]{1,40}$')`; NULL — без террейна. Список допустимых id проверяет API (`api/boards.LAYOUTS`, 422 `layout_unknown`), а не БД: новые раскладки добавляются без миграции.
- `boards.layout_swap boolean NOT NULL DEFAULT false` — игрок 1 в другой зоне высадки.
- С раскладкой API хранит размер 30″ × 22″. Существующие схемы получают NULL/false (без террейна), остальные таблицы не менялись; права роли приложения на `boards` прежние. Подробно — `22-v1.12.md`.

## v1.13 — 015_v113.sql

- `matches.conceded_slot smallint CHECK (conceded_slot IN (1,2))` — слот игрока, который сдался (действие `concede`); NULL — матч не сдан. `reopen` после спора очищает его.
- `match_players.operative_source varchar(8) CHECK (operative_source IN ('roster','team','manual'))` — откуда число оперативников: из прикреплённого ростера, по составу команды (`api/teams.composition`) или введено вручную. Числа из ростера и команды API пересчитывает при подготовке и старте (`teams.refresh_counts`); у матчей до 1.13 — NULL, их число не трогается.
- `local_players` (`id uuid` PK, `name varchar(64)` — `CHECK (btrim(name) <> '')`, `created_by` → users ON DELETE SET NULL, `created_at`) — общий список клуба: уникальный индекс `ks_fold(name)` (без учёта регистра и «ё»), одно имя — один человек для всех аккаунтов; лимит 300 записей на аккаунт проверяет API. `match_players.local_player_id` → local_players ON DELETE SET NULL (частичный индекс `(local_player_id, match_id)`): удаление записи администратором оставляет матчи с именем (`display_name`), но выводит их из рейтинга клуба. Гостевой `guest_opponents` у таких матчей создаётся, как раньше.
- `player_totals` пересоздано с теми же столбцами (как в 005): у сданного матча `vp` — 0 у сдавшегося и 10 у соперника, прочие компоненты (crit, tac, kill, бонус) не меняются. `player_results` и всё, что на нём построено (статистика, серии, Elo, сезоны, турниры), получают 10:0 без изменений.
- Роль приложения получает SELECT/INSERT/UPDATE/DELETE на `local_players` общим GRANT мигратора; остальные права прежние. Существующие данные не меняются. Подробно — `23-v1.13.md`.

## v1.14 — 016_v114.sql

- `match_players.equipment jsonb NOT NULL DEFAULT '[]'`, `CHECK (jsonb_typeof(equipment)='array' AND jsonb_array_length(equipment)<=4)` — снаряжение, выбранное игроком перед боем: серверные копии вариантов `{key, name, group, rules, weapons}` (клиент присылает только ключи), чтобы табло, калькулятор и история показывали текст, как играли. До старта API отдаёт сопернику только `equipment_count`; при старте снаряжение сверяется со справочником и раскрывается (аудит `equipment_reveal`).
- `match_cp_grants` (`match_id` → matches ON DELETE CASCADE, `turning_point int CHECK (0..12)`, `gains jsonb` — CP по слотам, например `{"1": 1, "2": 2}`, `granted_by` → users ON DELETE SET NULL, `created_at`), PK `(match_id, turning_point)`: 0 — 2CP после раскрытия снаряжения, 1–12 — шаг Ready поворотного момента. Ключ не даёт начислить дважды; сами CP — в `turning_point_states.cp`, как и ручные ±. «Отменить» удаляет запись и возвращает CP.
- `match_ploys` (`id bigint` identity, `match_id` → matches ON DELETE CASCADE, `player_id` → match_players ON DELETE CASCADE, `turning_point CHECK (1..12)`, `kind CHECK (kind IN ('strategy','firefight'))`, `name varchar(120)` непустое, `cost smallint CHECK (0..9)`, `used_by` → users ON DELETE SET NULL, `created_at`), индексы `(match_id, turning_point, id)` и `(player_id)` — протокол ploys матча и статистика `GET /api/stats/ploys`.
- `client_errors` (`id bigint` identity, `day date DEFAULT current_date`, `fingerprint char(64)`, `kind CHECK (kind IN ('error','rejection'))`, `message varchar(500)`, `source varchar(200)`, `stack varchar(2000)`, `page varchar(40)`, `version varchar(20)`, `agent varchar(160)`, `user_id` → users ON DELETE SET NULL, `count int CHECK (count >= 1)`, `first_at`, `last_at`), `UNIQUE (fingerprint, day)`, индекс `(last_at DESC)` — журнал ошибок браузера: одна строка на отпечаток и день, повтор увеличивает `count`; API удаляет записи старше 30 дней и не добавляет новые отпечатки сверх 5000 строк.
- Роль приложения получает SELECT/INSERT/UPDATE/DELETE на новые таблицы общим GRANT мигратора; остальные права прежние. Существующие данные не меняются. Подробно — `24-v1.14.md`.

## v1.15 — 017_v115.sql

- `matches.recorded_result boolean NOT NULL DEFAULT false`: отличает записанный итог между аккаунтами от партии, сыгранной на табло. Предыдущие строки остаются `false`. Очки хранятся в `turning_point_scores` как ручной итог; статус и права подтверждения — как у friend-матча. Миграция не удаляет данные.
