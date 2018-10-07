FROM python:3.7.0-alpine3.8

COPY requirements.txt /wormgas/requirements.txt

RUN /usr/local/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt

COPY . /wormgas

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]

LABEL maintainer=william@subtlecoolness.com \
      org.label-schema.schema-version=1.0 \
      org.label-schema.vcs-url=https://github.com/williamjacksn/wormgas \
      org.label-schema.version=3.0.1
