FROM python:3.9.5-alpine3.13

RUN /usr/sbin/adduser -g python -D python

USER python
RUN /usr/local/bin/python -m venv /home/python/venv

COPY requirements.txt /home/python/wormgas/requirements.txt
RUN /home/python/venv/bin/pip install --no-cache-dir --requirement /home/python/wormgas/requirements.txt

COPY . /home/python/wormgas

ENV APP_VERSION="2021.6" \
    PYTHONUNBUFFERED="1"

ENTRYPOINT ["/home/python/venv/bin/python"]
CMD ["/home/python/wormgas/run.py"]

LABEL org.opencontainers.image.authors="William Jackson <william@subtlecoolness.com>" \
      org.opencontainers.image.source="https://github.com/williamjacksn/wormgas" \
      org.opencontainers.image.version="${APP_VERSION}"
