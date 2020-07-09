FROM python:3.8.3-alpine3.12

COPY requirements.txt /wormgas/requirements.txt

RUN /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt

COPY . /wormgas

ENV APP_VERSION="2020.1" \
    PYTHONUNBUFFERED="1"

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL org.opencontainers.image.authors="William Jackson <william@subtlecoolness.com>" \
      org.opencontainers.image.source="https://github.com/williamjacksn/wormgas" \
      org.opencontainers.image.version="${APP_VERSION}"
