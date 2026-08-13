"""PDF PII redaction pipeline: Presidio (detection) + PyMuPDF (true content removal)."""

from __future__ import annotations

import io
import os
from typing import Optional

import fitz  # pymupdf
from presidio_analyzer import AnalyzerEngine, RecognizerRegistry
from presidio_analyzer.nlp_engine import NlpEngineProvider

from .pii_recognizers import CUSTOM_RECOGNIZERS

# en_core_web_lg (~400MB) gives the best PERSON/LOCATION detection and is what
# run.sh installs locally, but it won't fit a free-tier hosting plan's RAM budget.
# The Dockerfile used for hosted deployments overrides this to en_core_web_sm.
SPACY_MODEL = os.environ.get("SPACY_MODEL", "en_core_web_lg")

# Entities excluded from redaction by default. DATE_TIME is excluded because Presidio
# flags every date-shaped string (invoice dates, document versions, etc.) with no way
# to distinguish an ordinary business date from a birth date — for typical business
# documents that would redact far more than intended. URL is excluded for the same
# reason (reference links aren't personal information on their own).
EXCLUDED_ENTITIES = {"DATE_TIME", "URL"}
SCORE_THRESHOLD = 0.4

_analyzer: Optional[AnalyzerEngine] = None


def get_analyzer() -> AnalyzerEngine:
    global _analyzer
    if _analyzer is None:
        nlp_engine = NlpEngineProvider(
            nlp_configuration={
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": SPACY_MODEL}],
            }
        ).create_engine()
        registry = RecognizerRegistry()
        registry.load_predefined_recognizers()
        for recognizer in CUSTOM_RECOGNIZERS:
            registry.add_recognizer(recognizer)
        _analyzer = AnalyzerEngine(nlp_engine=nlp_engine, registry=registry)
    return _analyzer


def parse_exemptions(raw: str) -> list[str]:
    return [line.strip() for line in raw.splitlines() if line.strip()]


def redact_pdf_bytes(
    pdf_bytes: bytes,
    exemptions: list[str],
    must_redact: list[str] | None = None,
) -> bytes:
    """Return a copy of the given PDF with detected personal information permanently
    removed (not just visually covered). `must_redact` is a manual safety-net list -
    exact terms that get blacked out unconditionally, for cases (a specific name that
    automatic detection keeps missing, say) where you'd rather guarantee removal than
    rely on the model. Exemptions win if a term appears in both lists."""
    analyzer = get_analyzer()
    exempt_lower = {e.strip().lower() for e in exemptions}
    must_redact = [
        m.strip() for m in (must_redact or []) if m.strip() and m.strip().lower() not in exempt_lower
    ]

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in doc:
        page_text = page.get_text("text")
        if not page_text.strip():
            continue

        rects: list[fitz.Rect] = []

        # Analyze line-by-line rather than the whole page as one blob: spaCy's NER
        # will otherwise happily merge an entity across a line break (e.g. a name
        # bleeding into the next line's label text), which both mis-detects PII and
        # breaks exact-match exemptions since the "entity" text no longer matches
        # what the user typed in the exemptions box.
        for line in page_text.split("\n"):
            if not line.strip():
                continue
            results = analyzer.analyze(
                text=line,
                language="en",
                allow_list=exemptions or None,
            )
            for result in results:
                if result.entity_type in EXCLUDED_ENTITIES or result.score < SCORE_THRESHOLD:
                    continue
                snippet = line[result.start : result.end].strip()
                if snippet:
                    rects.extend(page.search_for(snippet))

        for term in must_redact:
            rects.extend(page.search_for(term))

        if rects:
            for rect in rects:
                page.add_redact_annot(rect, fill=(0, 0, 0))
            page.apply_redactions()

    out = io.BytesIO()
    doc.save(out, garbage=4, deflate=True)
    doc.close()
    return out.getvalue()
