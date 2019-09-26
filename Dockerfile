FROM python:3.7.4-alpine3.10

COPY requirements.txt /wormgas/requirements.txt

RUN /sbin/apk add --no-cache --virtual .deps git \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt \
 && /sbin/apk del --no-cache .deps

COPY . /wormgas

ENV PYTHONUNBUFFERED="1"

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL org.opencontainers.image.authors="William Jackson <william@subtlecoolness.com>" \
      org.opencontainers.image.source="https://github.com/williamjacksn/wormgas" \
      org.opencontainers.image.version=3.1.4
