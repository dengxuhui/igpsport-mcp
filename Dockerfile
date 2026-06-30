# Glama.ai 自动化评分 + 通用容器化支持
# Glama builds this image and runs introspection (initialize + tools/list) to audit/score.
# End users: stdio is the primary transport; this image serves registry introspection.

FROM python:3.12-slim

LABEL io.modelcontextprotocol.server.name="io.github.dengxuhui/igpsport-mcp"

WORKDIR /app

# Install from PyPI (includes vendored wasm + all deps)
RUN pip install --no-cache-dir igpsport-mcp

# stdio MCP server (registries probe with initialize → tools/list)
ENTRYPOINT ["igpsport-mcp"]
