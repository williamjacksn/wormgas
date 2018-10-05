FROM python:3.7.0-alpine3.8

COPY requirements.txt /wormgas/requirements.txt

RUN /usr/local/bin/pip install --no-cache-dir --upgrade pip setuptools wheel \
 && /usr/local/bin/pip install --no-cache-dir --requirement /wormgas/requirements.txt

COPY . /wormgas

ENTRYPOINT ["/usr/local/bin/python"]
CMD ["/wormgas/run.py"]
