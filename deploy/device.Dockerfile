FROM python:3.12-slim-bookworm AS dlib-builder
ENV DEBIAN_FRONTEND=noninteractive CMAKE_BUILD_PARALLEL_LEVEL=2
RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get -o Acquire::Retries=3 update \
    && apt-get -o Acquire::Retries=3 install -y --no-install-recommends cmake make g++ \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1
RUN pip wheel --no-cache-dir --no-build-isolation --no-deps --wheel-dir /wheels dlib==19.24.6

FROM python:3.12-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
# The runtime contains no compiler, GUI toolkit or device-specific driver.
COPY --from=dlib-builder /wheels /wheels
RUN pip install --no-cache-dir --no-index /wheels/*.whl && rm -rf /wheels
RUN pip install --no-cache-dir setuptools==80.9.0 wheel==0.45.1
RUN pip install --no-cache-dir --no-build-isolation numpy==1.26.4 opencv-python-headless==4.11.0.86 Pillow==12.3.0 Flask==3.1.3 requests==2.34.2 cryptography==50.0.1 spake2==0.9 gunicorn==26.2.0 face-recognition-models==0.3.0 click==8.5.0 \
    && pip install --no-cache-dir --no-deps face-recognition==1.3.0
RUN groupadd -g 10001 smartlock && useradd -u 10001 -g smartlock smartlock && mkdir /data && chown smartlock:smartlock /data
WORKDIR /app
COPY packages/smartlock_protocol /opt/smartlock_protocol
RUN pip install --no-cache-dir --no-deps /opt/smartlock_protocol
COPY paspberry_pi/*.py /app/
COPY paspberry_pi/cv/code/*.py /app/cv/code/
COPY paspberry_pi/tests /app/tests
COPY deploy/device_smoke.py /app/device_smoke.py
USER 10001:10001
CMD ["gunicorn", "--config", "/app/gunicorn.conf.py", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "2", "--timeout", "60", "--access-logfile", "-", "app:app"]
