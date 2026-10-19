FROM python:3.12-slim
RUN useradd --create-home app
WORKDIR /app
# Pinned runtime deps first (cached layer), then the package itself without re-resolving them.
COPY requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir --no-deps .
USER app
ENTRYPOINT ["scraper"]
