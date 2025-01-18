FROM python:3.12-slim

# install deps requried for compiling C modules
RUN apt update
RUN apt-get install gcc git -y

RUN mkdir /app
WORKDIR /app

COPY ./node ./node
COPY README.md ./
COPY pyproject.toml ./
COPY poetry.lock ./

# poetry's configuration
ENV POETRY_NO_INTERACTION=1 \
  POETRY_VIRTUALENVS_CREATE=false \
  POETRY_CACHE_DIR='/app/.cache/pypoetry' \
  POETRY_HOME='/app/.poetry' \
  POETRY_VERSION=1.8.4

# install poetry
RUN pip install poetry

# install
RUN poetry lock && poetry install --only=main --no-interaction --no-ansi --no-root

CMD poetry run celery -A node.worker.main:app worker --loglevel=info
