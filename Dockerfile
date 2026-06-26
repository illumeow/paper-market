FROM python:3.11-slim
WORKDIR /srv
COPY pyproject.toml ./
RUN pip install --no-cache-dir . && pip install --no-cache-dir uvicorn[standard]
COPY app ./app
COPY config ./config
COPY scripts ./scripts
COPY frontend ./frontend
RUN mkdir -p /data
ENV DB_PATH=/data/paper.db
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
