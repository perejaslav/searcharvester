FROM nousresearch/hermes-agent:latest

USER root

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

RUN uv pip install --no-cache-dir --python /opt/hermes/.venv/bin/python3 \
    "trafilatura>=1.12,<3.0" \
    "lxml>=4.9" \
    "beautifulsoup4==4.12.2" \
    "sse-starlette==2.1.3"

RUN mkdir -p /app && chown hermes:hermes /app
COPY --chown=hermes:hermes . /app/

COPY --chown=root:root docker/entrypoint-adapter.sh /entrypoint-adapter.sh
RUN chmod +x /entrypoint-adapter.sh

WORKDIR /app
EXPOSE 8000

ENTRYPOINT ["/entrypoint-adapter.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
