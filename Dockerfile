FROM python:3.7.2-alpine3.9

COPY requirements.txt /wormgas/requirements.txt

RUN /sbin/apk add --no-cache --virtual .deps git \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt \
 && /sbin/apk del --no-cache .deps

COPY . /wormgas

ENV PYTHONUNBUFFERED 1

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL maintainer=william@subtlecoolness.com \
      org.label-schema.schema-version=1.0 \
      org.label-schema.vcs-url=https://github.com/williamjacksn/wormgas \
      org.label-schema.version=3.1.1
