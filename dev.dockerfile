FROM python:3.8 as builder
ENV POETRY_NO_INTERACTION=1
RUN pip install poetry
RUN poetry config virtualenvs.create false
WORKDIR /spellbot

COPY pyproject.toml ./
COPY poetry.lock ./
COPY README.md ./
RUN poetry install --no-root
COPY src ./src
RUN poetry install

CMD ["spellbot","--log-level","INFO","run","--dev"]
