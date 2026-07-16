FROM python:3.12.4
WORKDIR /app

COPY README.md pyproject.toml overrides.py ./
COPY api ./api

RUN pip install .

EXPOSE 5000
CMD ["gunicorn", "-b", ":5000", "-w", "5", "--timeout", "120", "api.app:app"]