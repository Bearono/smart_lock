FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY BE_smart_lock/smart_lock/requirements.txt BE_smart_lock/smart_lock/requirements.lock /app/
RUN pip install --no-cache-dir -r requirements.txt
RUN groupadd -g 10001 smartlock && useradd -u 10001 -g smartlock smartlock && mkdir /data && chown smartlock:smartlock /data
COPY BE_smart_lock/smart_lock/app /app/app
COPY BE_smart_lock/smart_lock/config.py BE_smart_lock/smart_lock/run.py /app/
COPY deploy/backup.py /app/backup.py
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
