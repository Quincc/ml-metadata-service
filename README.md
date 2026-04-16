# ML Metadata Management Service

Сервис для управления метаданными ML pipeline на `FastAPI`.
Проект хранит не сами датасеты, а информацию о них: источник, датасет, версии данных, версии схем, feature sets, эксперименты и lineage между сущностями.

В проекте есть:
- REST API на `FastAPI`
- встроенный UI на `Jinja2`
- локальный офлайн-скрипт для HTMX-подобного поведения
- PostgreSQL через `SQLAlchemy`
- миграции через `Alembic`
- запуск через `uv` и `Docker`

## Что умеет система

- регистрировать источники данных
- регистрировать датасеты
- хранить версии датасетов
- хранить версии схем
- хранить наборы признаков
- хранить эксперименты
- строить lineage для сущности
- поддерживать soft delete для основных сущностей

Основная идея: показать происхождение данных от источника до ML-эксперимента.

## Структура проекта

```text
app/
  data/
    Titanic-Dataset.csv
  models/
  routers/
  schemas/
  services/
  static/
  templates/
    ui/
  db.py
  main.py
scripts/
  preprocess_titanic.py
alembic/
  env.py
  versions/
data/
  train_cleaned.csv
  train_cleaned_schema.json
Dockerfile
docker-compose.yml
pyproject.toml
requirements.txt
alembic.ini
uv.lock
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

Если база была создана до настройки Alembic и уже содержит исходную схему, можно сначала отметить стартовую ревизию:

```bash
uv run alembic stamp 20260416_0001
uv run alembic upgrade head
```

Примечание: сейчас приложение в dev-режиме также создает таблицы при старте через `Base.metadata.create_all(...)`. Для контролируемого изменения схемы основной способ все равно `Alembic`.

## Основные сущности

- `DataSource` — источник данных
- `Dataset` — логический датасет
- `SchemaVersion` — версия схемы датасета
- `DatasetVersion` — версия данных
- `FeatureSet` — набор признаков
- `Experiment` — ML-эксперимент
- `LineageEdge` — связь между сущностями

## Типовой сценарий работы

1. Создать источник данных.
2. Создать датасет.
3. Создать версию схемы.
4. Создать версию датасета.
5. Создать feature set.
6. Создать эксперимент.
7. Посмотреть lineage через UI или API.

Пример цепочки:

```text
source -> dataset -> dataset_version -> feature_set -> experiment
```

## Пример с Titanic

В проекте есть учебный сценарий для датасета Titanic.

Исходный файл:

```text
app/data/Titanic-Dataset.csv
```

Скрипт preprocessing:

```bash
uv run python scripts/preprocess_titanic.py \
  --input app/data/Titanic-Dataset.csv \
  --output data/train_cleaned.csv \
  --schema-output data/train_cleaned_schema.json
```

Скрипт:
- заполняет пропуски в `Age`
- заполняет пропуски в `Fare`
- заполняет пропуски в `Embarked`
- создает `FamilySize`
- кодирует `Sex` в `SexEncoded`
- кодирует `Embarked` в `EmbarkedEncoded`
- удаляет лишние текстовые поля
- сохраняет очищенный CSV и JSON-схему

После выполнения появятся:
- `data/train_cleaned.csv`
- `data/train_cleaned_schema.json`

Дальше можно:
- зарегистрировать `Titanic CSV` как `Data Source`
- создать датасет `titanic_survival`
- добавить `Schema Version` из `train_cleaned_schema.json`
- добавить `Dataset Version`
- создать `Feature Set`
- создать `Experiment`
- открыть lineage в `/ui`

## Проверка API

Проще всего тестировать через Swagger:

```text
http://localhost:8000/docs
```

Минимальная последовательность:

1. `POST /sources`
2. `POST /datasets`
3. `POST /datasets/{id}/schema`
4. `POST /datasets/{id}/versions`
5. `POST /features`
6. `POST /experiments`
7. `GET /lineage/{entity_type}/{entity_id}`

## Soft Delete

Для основных сущностей поддерживается мягкое удаление.
Это позволяет не ломать историю и lineage физическим удалением записей.

## Локальный запуск через pip

Если `uv` не нужен, можно запустить и так:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/metadata_db
uvicorn app.main:app --reload
```
