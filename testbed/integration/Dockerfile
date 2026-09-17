FROM python:3.13-slim

WORKDIR /workspace

RUN pip install --no-cache-dir \
    jsonschema==4.26.0 \
    paho-mqtt==2.1.0

COPY testbed /workspace/testbed

ENV PYTHONUNBUFFERED=1
