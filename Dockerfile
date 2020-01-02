FROM python:3.8.1-alpine3.11

COPY requirements.txt /wormgas/requirements.txt

RUN /sbin/apk add --no-cache --virtual .deps gcc musl-dev \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt \
 && /sbin/apk del --no-cache .deps

COPY . /wormgas

ENV APP_VERSION="2020.1" \
    PYTHONUNBUFFERED="1"

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL org.opencontainers.image.authors="William Jackson <william@subtlecoolness.com>" \
      org.opencontainers.image.source="https://github.com/williamjacksn/wormgas" \
      org.opencontainers.image.version="${APP_VERSION}"
