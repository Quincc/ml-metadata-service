# ML Metadata Management Service

Сервис для управления метаданными ML pipeline на `FastAPI`.
Проект хранит не сами датасеты, а сведения о них: источник, датасет, версии данных, версии схем, feature sets, эксперименты и lineage между сущностями.

В проекте есть:
- REST API на `FastAPI`
- встроенный UI на `Jinja2` + `htmx` 1.9.12
- интерактивный граф lineage (`vis-network`)
- PostgreSQL через `SQLAlchemy 2`
- миграции через `Alembic`
- настройки через `pydantic-settings`
- запуск через `uv` и `Docker Compose`
- pytest + GitHub Actions CI

## Что умеет система

- регистрировать источники данных, датасеты, версии схем и данных, feature sets, эксперименты, модели
- автоматически инферить схему из CSV-файла
- строить lineage от источника до модели (граф с кликабельными узлами)
- хранить параметры/метрики эксперимента, его статус (`created` / `running` / `finished` / `failed`) и артефакты (notebook URL, путь к отчёту)
- регистрировать модели (`Model`), произведённые экспериментом
- soft-delete с архивом и восстановлением через UI
- единые ошибки API (`IntegrityError → 409`, `ValueError → 400`)

Основная идея: показать происхождение данных от источника до обученной модели.

## Структура проекта

```text
app/
  models/             # SQLAlchemy ORM (Dataset, Experiment, Model, ...)
  routers/            # REST + UI endpoints
  schemas/            # Pydantic схемы
  services/           # бизнес-логика (lineage, versioning, schema_inference)
  templates/          # Jinja2 (base, dashboard, dataset_detail, experiment_detail, archive, lineage)
  static/             # htmx, vis-network, styles.css
  db.py               # engine + Session + Base
  exceptions.py       # глобальные обработчики ошибок
  main.py
  settings.py         # pydantic-settings
alembic/versions/     # миграции (0001..0007)
test/                 # pytest (smoke + e2e сценарии)
scripts/
  preprocess_titanic.py
  seed_demo_metadata.py
data/
  raw/ processed/ schemas/
.github/workflows/ci.yml
Dockerfile docker-compose.yml pyproject.toml uv.lock alembic.ini
```

## Технологии

- `Python 3.12`
- `FastAPI`
- `SQLAlchemy 2`
- `PostgreSQL`
- `Pydantic 2`
- `Alembic`
- `uv`
- `Docker Compose`

## Быстрый старт через uv

1. Установите зависимости:

```bash
uv sync
```

2. Убедитесь, что PostgreSQL доступен на `localhost:5432`.

Строка подключения по умолчанию:

```text
postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db
```

3. При необходимости задайте `DATABASE_URL`:

```bash
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db
```

4. Примените миграции:

```bash
uv run alembic upgrade head
```

5. Запустите приложение:

```bash
uv run uvicorn app.main:app --reload
```

## Запуск через Docker

Для разработки уже настроен hot reload.

```bash
docker compose up --build
```

Что происходит:
- запускается `PostgreSQL`
- запускается API на `8000`
- изменения в `app/` подхватываются автоматически
- `uvicorn` перезапускается при сохранении `py`, `html`, `css`, `js`

Если нужно пересобрать окружение с нуля:

```bash
docker compose down -v
docker compose up --build
```

## Полезные адреса

- `http://localhost:8000/ui` — встроенный интерфейс
- `http://localhost:8000/docs` — Swagger UI
- `http://localhost:8000/health` — health-check

Корневой маршрут `/` делает редирект на `/ui`.

## Подключение к базе данных

Если база поднята через `docker compose`, подключение с хоста такое:

- `host`: `localhost`
- `port`: `5432`
- `database`: `metadata_db`
- `user`: `postgres`
- `password`: `postgres`

Примеры:

```bash
PGPASSWORD=postgres psql -h localhost -p 5432 -U postgres -d metadata_db
```

```bash
docker compose exec db psql -U postgres -d metadata_db
```

## Alembic

Миграции лежат в `alembic/versions`.

Применить миграции:

```bash
uv run alembic upgrade head
```

Посмотреть текущую ревизию:

```bash
uv run alembic current
```

Создать новую миграцию после изменения моделей:

```bash
uv run alembic revision --autogenerate -m "describe change"
```

Если база уже содержит схему, но запись в `alembic_version` отсутствует — стампить вручную:

```bash
uv run alembic stamp 20260509_0007
```

Создать таблицы через `Base.metadata.create_all(...)` приложение **не** делает — единственный путь — `alembic upgrade head` (запускается автоматически в Docker).

## Основные сущности

- `DataSource` — источник данных
- `Dataset` — логический датасет
- `SchemaVersion` — версия схемы датасета
- `DatasetVersion` — версия данных
- `FeatureSet` — набор признаков
- `Experiment` — ML-эксперимент со статусом и артефактами
- `Model` — обученная модель, привязанная к эксперименту
- `LineageEdge` — связь между сущностями
- `AuditLog` — журнал создания, архивирования и восстановления сущностей

## Типовой сценарий работы

```text
source → dataset → schema_version → dataset_version → feature_set → experiment → model
```

1. `POST /sources` — источник данных
2. `POST /datasets` — датасет
3. `POST /datasets/{id}/schema` (или `/schema/from-csv` для автоинфера)
4. `POST /datasets/{id}/versions`
5. `POST /features`
6. `POST /experiments` (можно сразу с `status="running"`, `notebook_url`, `report_path`)
7. `PATCH /experiments/{id}/status` — обновить статус (`finished` / `failed`)
8. `POST /models` — зафиксировать обученную модель
9. `GET /lineage/{entity_type}/{entity_id}` — посмотреть граф

## Демо-данные за один шаг

Заполнить БД готовым каталогом (3 источника, 3 датасета, 7 экспериментов, 7 моделей, 41 lineage-edge):

```bash
uv run python scripts/seed_demo_metadata.py
```

После этого откройте `http://localhost:8000/ui` — на дашборде заполнены все таблицы. В Lineage Explorer выберите `model` / `1` или `source` / `1` — увидите цепочку.

## Пример с Titanic

В проекте есть учебный сценарий с датасетом Titanic.

```text
data/raw/titanic_dataset.csv      # исходный файл
data/processed/train_cleaned.csv  # подготовленные данные
data/schemas/train_cleaned_schema.json
```

Скрипт preprocessing:

```bash
uv run python scripts/preprocess_titanic.py \
  --input data/raw/titanic_dataset.csv \
  --output data/processed/train_cleaned.csv \
  --schema-output data/schemas/train_cleaned_schema.json
```

Сценарий демо в UI:

1. Откройте `/ui` → видите дашборд (если запустили seed — данные уже там).
2. Кликните по `titanic_survival` в таблице Datasets — откроется детальная страница.
3. На странице — версии схем, версии данных, feature sets, lineage-граф этого датасета.
4. Загрузите `data/raw/titanic_dataset.csv` через форму **Infer schema from CSV** — появится новая schema version с автоинферированными типами.
5. Вернитесь на дашборд → клик по эксперименту `titanic_xgboost_tuned` → детальная страница с метриками и graph rooted at experiment.
6. На графе кликните по узлу `model` — перерисуется lineage относительно модели.
7. Архивируйте эксперимент → проверьте `/ui/archive` → восстановите.

## Soft Delete и архив

Для всех основных сущностей — мягкое удаление через `deleted_at`. Архивные сущности скрыты с дашборда, доступны на `/ui/archive` с кнопкой Restore. Lineage-история сохраняется.

## Тесты

```bash
uv run pytest
```

14 тестов покрывают: health-check, рендер UI, full pipeline source→model, статусы эксперимента, архив + restore, IntegrityError → 409, CSV schema inference, создание dataset version из CSV, поиск датасетов, audit log, экспорт отчётов и детальные страницы.

CI на GitHub Actions запускает `pytest` при push/PR в `main` ([.github/workflows/ci.yml](.github/workflows/ci.yml)).

## Локальный запуск через pip

Если `uv` не нужен, можно запустить и так:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db
uvicorn app.main:app --reload
```

## License

MIT
