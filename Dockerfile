# AuditGym — offline verification image. Zero runtime dependencies (Python 3.11 stdlib only).
# Pin the base image by digest before submitting:
#   docker buildx imagetools inspect python:3.11-slim-bookworm   -> copy the sha256 digest
#   FROM python:3.11-slim-bookworm@sha256:<digest>
FROM python:3.11-slim-bookworm@sha256:a83ba18aef0f865b1a4a611c2cf460fe446f2795673bbb9fe43be570439e3b39

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/src
WORKDIR /app
COPY src/ /app/src/
COPY configs/ /app/configs/
COPY tests/ /app/tests/
COPY episodes/ /app/episodes/
COPY README.md DESIGN.md LICENSE requirements.txt /app/
RUN useradd --create-home --uid 10001 auditor && mkdir -p /work && chown auditor /work
USER auditor
WORKDIR /work
EXPOSE 8000
ENTRYPOINT ["python", "-m", "auditgym.cli"]
# Default: the one verification command. Others: demo | ui --host 0.0.0.0 --no-browser | serve --stdio
CMD ["verify", "--out", "/work/report.json", "--trajectories", "/work/trajectories.jsonl"]
