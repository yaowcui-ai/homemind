FROM python:3.12-slim-bookworm@sha256:e697c81897302a4c4333bade000d98038fbb21eb064f8ee1fd42d02ebcd9d337

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_NO_CACHE=1
WORKDIR /app
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups --no-install-project
COPY src ./src
RUN uv sync --frozen --no-default-groups --no-editable \
    && useradd --uid 10001 --create-home homemind
ENV PATH="/app/.venv/bin:$PATH"
USER 10001:10001
EXPOSE 8100
CMD ["python", "-m", "homemind"]
