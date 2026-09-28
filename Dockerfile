FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DOCATLAS_DATA_DIR=/app/data
WORKDIR /app
COPY pyproject.toml requirements.lock ./
COPY src ./src
RUN pip install --no-cache-dir -c requirements.lock '.[semantic]' \
    && useradd --create-home --uid 10001 docatlas \
    && mkdir /app/data && chown -R docatlas:docatlas /app/data
USER docatlas
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["docatlas", "serve", "--host", "0.0.0.0", "--port", "8000"]
