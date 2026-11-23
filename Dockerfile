# ReproLens: the web app, with OCR built in.
#
#   docker build -t reprolens .
#   docker run --rm -p 8765:8765 reprolens
#
# Figures are read by a vision model that does not ship in this image. Point it
# at an Ollama on the host:
#   docker run --rm -p 8765:8765 -e OLLAMA_HOST=http://host.docker.internal:11434 reprolens
# or use Claude instead:
#   docker run --rm -p 8765:8765 -e REPROLENS_VLM=anthropic -e ANTHROPIC_API_KEY=... reprolens
# With neither, the page says so and the audit runs without reading figures.

FROM python:3.11-slim

# tesseract for scanned pages; git to fetch the repositories a paper names
# (fetched and parsed, never executed).
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.8.4 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy

COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

COPY audit.py ./
COPY reprolens ./reprolens
COPY app ./app
COPY prompts ./prompts

RUN useradd --create-home reprolens && chown -R reprolens /app
USER reprolens

ENV REPROLENS_HOST=0.0.0.0 REPROLENS_PORT=8765 PATH="/app/.venv/bin:$PATH"
EXPOSE 8765
CMD ["python", "-m", "app.server"]
