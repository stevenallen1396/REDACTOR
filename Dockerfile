FROM python:3.12-slim

# WeasyPrint renders via Pango/cairo/gdk-pixbuf through ctypes (no system Python
# bindings needed), but the shared libraries themselves must be present. Liberation
# and DejaVu give reasonable Arial/Helvetica-metric-compatible + broad Unicode glyph
# coverage for rendered emails without needing the full macOS font set this app can
# lean on when run locally.
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libglib2.0-0 \
    libffi8 \
    shared-mime-info \
    fonts-liberation \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# en_core_web_lg (~400MB) is what run.sh installs for local use, but it won't fit a
# free-tier hosting plan's RAM budget. Hosted deployments use the much lighter
# en_core_web_sm instead (see SPACY_MODEL below) - accuracy is somewhat lower,
# particularly for PERSON detection, which is a deliberate trade-off for this
# environment. Always spot-check output either way.
ARG SPACY_MODEL=en_core_web_sm
RUN python -m spacy download ${SPACY_MODEL}
ENV SPACY_MODEL=${SPACY_MODEL}

COPY backend backend
COPY frontend frontend

ENV PORT=8420
EXPOSE 8420

CMD ["sh", "-c", "cd backend && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
