from __future__ import annotations

import io
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles

from .auth import BasicAuthMiddleware
from .email_to_pdf import convert_email_to_pdf
from .redact import parse_exemptions, redact_pdf_bytes

MAX_FILES = 100
MAX_FILE_SIZE = 30 * 1024 * 1024  # 30MB

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"

app = FastAPI(title="The REDACTOR")
app.add_middleware(BasicAuthMiddleware)


def _zip_response(files: list[tuple[str, bytes]]) -> StreamingResponse:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in files:
            zf.writestr(name, data)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="output.zip"'},
    )


async def _read_and_validate(files: list[UploadFile]) -> list[tuple[str, bytes]]:
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files (max {MAX_FILES})")

    loaded = []
    for f in files:
        data = await f.read()
        if len(data) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=400,
                detail=f"{f.filename} exceeds the {MAX_FILE_SIZE // (1024 * 1024)}MB limit",
            )
        loaded.append((f.filename or "file", data))
    return loaded


@app.post("/api/redact")
async def api_redact(
    files: list[UploadFile] = File(...),
    exemptions: str = Form(""),
):
    loaded = await _read_and_validate(files)
    exemption_list = parse_exemptions(exemptions)

    results = []
    for filename, data in loaded:
        if not filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail=f"{filename} is not a PDF")
        try:
            redacted = redact_pdf_bytes(data, exemption_list)
        except Exception as exc:  # surface per-file failures without killing the batch
            raise HTTPException(status_code=422, detail=f"Failed to redact {filename}: {exc}")
        path = Path(filename)
        output_name = str(path.with_name(f"{path.stem}_redacted{path.suffix}"))
        results.append((output_name, redacted))

    return _zip_response(results)


@app.post("/api/process")
async def api_process(
    files: list[UploadFile] = File(...),
    exemptions: str = Form(""),
):
    """Accepts a mixed batch (PDFs alongside .eml/.msg): email files are converted
    to PDF first, then every PDF - original or converted - is redacted, and the
    whole batch comes back as one ZIP."""
    loaded = await _read_and_validate(files)
    exemption_list = parse_exemptions(exemptions)

    results = []
    for filename, data in loaded:
        suffix = Path(filename).suffix.lower()
        if suffix in (".eml", ".msg"):
            try:
                pdf_bytes = convert_email_to_pdf(filename, data)
            except Exception as exc:
                raise HTTPException(status_code=422, detail=f"Failed to convert {filename}: {exc}")
            source_name = str(Path(filename).with_suffix(".pdf"))
        elif suffix == ".pdf":
            pdf_bytes = data
            source_name = filename
        else:
            raise HTTPException(
                status_code=400, detail=f"{filename} is not a PDF, .eml, or .msg file"
            )

        try:
            redacted = redact_pdf_bytes(pdf_bytes, exemption_list)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to redact {filename}: {exc}")
        path = Path(source_name)
        output_name = str(path.with_name(f"{path.stem}_redacted{path.suffix}"))
        results.append((output_name, redacted))

    return _zip_response(results)


@app.post("/api/convert-email")
async def api_convert_email(files: list[UploadFile] = File(...)):
    loaded = await _read_and_validate(files)

    results = []
    for filename, data in loaded:
        suffix = Path(filename).suffix.lower()
        if suffix not in (".eml", ".msg"):
            raise HTTPException(status_code=400, detail=f"{filename} is not .eml or .msg")
        try:
            pdf_bytes = convert_email_to_pdf(filename, data)
        except Exception as exc:
            raise HTTPException(status_code=422, detail=f"Failed to convert {filename}: {exc}")
        output_name = str(Path(filename).with_suffix(".pdf"))
        results.append((output_name, pdf_bytes))

    return _zip_response(results)


if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
