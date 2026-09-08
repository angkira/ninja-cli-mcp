FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOME=/home/ninja \
    PATH=/home/ninja/.local/bin:$PATH \
    XDG_CACHE_HOME=/home/ninja/.cache \
    NINJA_CACHE_DIR=/home/ninja/.cache/ninja-mcp

RUN apt-get update \
    && apt-get install --no-install-recommends -y git \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash ninja \
    && mkdir -p /workspace /home/ninja/.ninja /home/ninja/.cache/ninja-mcp \
    && chown -R ninja:ninja /workspace /home/ninja

WORKDIR /workspace
COPY --chown=ninja:ninja . /opt/ninja-mcp

USER ninja
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir "/opt/ninja-mcp[coder,researcher,secretary,agent]"

COPY --chown=ninja:ninja docker/entrypoint.sh /usr/local/bin/ninja-container
COPY --chown=ninja:ninja docker/healthcheck.sh /usr/local/bin/ninja-healthcheck
RUN chmod 0755 /usr/local/bin/ninja-container /usr/local/bin/ninja-healthcheck

ENTRYPOINT ["/usr/local/bin/ninja-container"]
CMD ["ninja-mcp", "--help"]
