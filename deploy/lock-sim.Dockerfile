FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY apps/lock_sim/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt \
    && groupadd -g 10001 smartlock && useradd -u 10001 -g smartlock smartlock \
    && mkdir /data && chown smartlock:smartlock /data
COPY packages/smartlock_protocol /opt/smartlock_protocol
RUN pip install --no-cache-dir --no-deps /opt/smartlock_protocol
COPY apps/lock_sim/*.py /app/
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:5444", "--workers", "1", "--threads", "2", "--timeout", "15", "--certfile", "/run/tls/server.crt", "--keyfile", "/run/tls/server.key", "service:from_environment()"]
