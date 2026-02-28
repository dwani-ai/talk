FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py config.py models.py deps.py .
COPY routers/ routers/
COPY services/ services/

EXPOSE 8000

CMD ["gunicorn", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000", "main:app", "--access-logfile", "-", "--error-logfile", "-"]
