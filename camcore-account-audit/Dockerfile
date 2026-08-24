FROM python:3.13.13-alpine@sha256:420cd0bf0f3998275875e02ecd5808168cf0843cbb4d3c536432f729247b2acc

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY audit.py /app/audit.py

RUN addgroup -S -g 10001 audit \
    && adduser -S -D -H -u 10001 -G audit audit \
    && mkdir -p /data \
    && chown audit:audit /data \
    && python -m py_compile /app/audit.py

USER 10001:10001

VOLUME ["/data"]

ENTRYPOINT ["python", "/app/audit.py"]
