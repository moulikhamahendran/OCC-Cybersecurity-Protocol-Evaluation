FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    asyncua==2.0.1 \
    psutil==7.2.2

COPY testbed/protocols/opcua /app/testbed/protocols/opcua
COPY testbed/vehicles /app/vehicles

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "-u", "testbed/protocols/opcua/opcua_server.py"]
