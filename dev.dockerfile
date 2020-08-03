FROM python:3.8 as builder

COPY . /spellbot
WORKDIR /spellbot
RUN pip install poetry
RUN poetry config virtualenvs.create false
RUN poetry install
CMD ["spellbot","--log-level","INFO","run","--dev"]
