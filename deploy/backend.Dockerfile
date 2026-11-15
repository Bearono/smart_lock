FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/api/requirements.txt apps/api/requirements.lock /app/
RUN pip install --no-cache-dir -r requirements.txt
COPY packages/smartlock_protocol /opt/smartlock_protocol
RUN pip install --no-cache-dir --no-deps /opt/smartlock_protocol
RUN groupadd -g 10001 smartlock && useradd -u 10001 -g smartlock smartlock && mkdir /data && chown smartlock:smartlock /data
COPY apps/api/app /app/app
COPY apps/api/config.py apps/api/run.py /app/
COPY deploy/backup.py /app/backup.py
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "2", "--threads", "4", "--timeout", "60", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
