FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir redis==5.0.0

COPY run-tests.py /app/run-tests.py

CMD ["python", "/app/run-tests.py"]
