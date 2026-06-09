# LNAIME 脳コンテナ v0（校正API）。host環境を汚さず再現可能に。
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
        sudachipy \
        sudachidict_core \
        pyyaml \
        fastapi \
        "uvicorn[standard]"

COPY app/ /app/

ENV LNAIME_MASTER=/app/dict/master.yaml
EXPOSE 8000

CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000"]
