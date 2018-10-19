FROM python:3.7.0-alpine3.8

COPY requirements-docker.txt /wormgas/requirements-docker.txt

RUN /sbin/apk --no-cache add --virtual .deps git \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements-docker.txt \
 && /sbin/apk del .deps

COPY . /wormgas

ENV PYTHONUNBUFFERED 1

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL maintainer=william@subtlecoolness.com \
      org.label-schema.schema-version=1.0 \
      org.label-schema.vcs-url=https://github.com/williamjacksn/wormgas \
      org.label-schema.version=3.0.1
