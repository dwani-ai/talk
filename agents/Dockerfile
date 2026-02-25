FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/agents-requirements.txt
RUN pip install --no-cache-dir -r /app/agents-requirements.txt

COPY . /app

ENV AGENTS_APP_NAME=talk_travel_planner

EXPOSE 8081

CMD ["uvicorn", "service_main:app", "--host", "0.0.0.0", "--port", "8081"]

