"""
 Copyright 2024 Adobe
 All Rights Reserved.

 NOTICE: Adobe permits you to use, modify, and distribute this file in
 accordance with the terms of the Adobe license agreement accompanying it.
"""

import io
import json
import logging
import os
import re
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import ExtractElementType
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import ExtractPDFParams
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult

logging.basicConfig(level=logging.INFO)


@dataclass
class PIIFinding:
    """A single regex match with optional PDF coordinates (user space)."""

    pii_type: str
    matched_text: str
    page: int
    path: str | None
    bounds: list[float] | None
    char_start: int
    char_end: int


# Demo patterns only — tune for your jurisdiction and false-positive tolerance.
DEFAULT_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    ("us_phone", re.compile(r"\b(?:\+?1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("us_ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    (
        "credit_card_like",
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    ),
]


def _union_rects(rects: list[list[float]]) -> list[float] | None:
    if not rects:
        return None
    left = min(r[0] for r in rects)
    bottom = min(r[1] for r in rects)
    right = max(r[2] for r in rects)
    top = max(r[3] for r in rects)
    return [left, bottom, right, top]


def _bounds_for_span(
    text: str,
    char_bounds: list[list[float]] | None,
    element_bounds: list[float] | None,
    start: int,
    end: int,
) -> list[float] | None:
    if char_bounds is not None and len(char_bounds) == len(text) and start < end:
        span_bounds = char_bounds[start:end]
        return _union_rects(span_bounds)
    if element_bounds is not None and len(element_bounds) == 4:
        return list(element_bounds)
    return None


def scan_structured_data_for_pii(
    data: dict[str, Any],
    patterns: list[tuple[str, re.Pattern[str]]] | None = None,
) -> list[PIIFinding]:
    patterns = patterns or DEFAULT_PII_PATTERNS
    findings: list[PIIFinding] = []
    for element in data.get("elements", []):
        text = element.get("Text") or ""
        if not text.strip():
            continue
        page = int(element.get("Page", 0))
        path = element.get("Path")
        if isinstance(path, list):
            path_str = "/".join(str(p) for p in path)
        else:
            path_str = str(path) if path is not None else None
        eb = element.get("Bounds")
        element_bounds: list[float] | None = (
            [float(x) for x in eb] if isinstance(eb, list) and len(eb) == 4 else None
        )
        cb = element.get("CharBounds")
        char_bounds: list[list[float]] | None = None
        if isinstance(cb, list) and cb:
            char_bounds = []
            for row in cb:
                if isinstance(row, list) and len(row) == 4:
                    char_bounds.append([float(x) for x in row])
                else:
                    char_bounds = None
                    break

        for pii_type, pattern in patterns:
            for m in pattern.finditer(text):
                b = _bounds_for_span(text, char_bounds, element_bounds, m.start(), m.end())
                findings.append(
                    PIIFinding(
                        pii_type=pii_type,
                        matched_text=m.group(0),
                        page=page,
                        path=path_str,
                        bounds=b,
                        char_start=m.start(),
                        char_end=m.end(),
                    )
                )
    return findings


#
# Extract PDF text with per-character bounds, then run regex-based PII detection
# and write a JSON report (matches + PDF coordinates where available).
#
# Refer to README.md for how to run samples and how Extract ZIP output is structured.
#
class ScanPIIFromPDF:
    def __init__(self):
        try:
            with open("src/resources/extractPdfInput.pdf", "rb") as file:
                input_stream = file.read()

            credentials = ServicePrincipalCredentials(
                client_id=os.getenv("PDF_SERVICES_CLIENT_ID"),
                client_secret=os.getenv("PDF_SERVICES_CLIENT_SECRET"),
            )

            pdf_services = PDFServices(credentials=credentials)

            input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)

            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[ExtractElementType.TEXT],
                add_char_info=True,
            )

            extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)

            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)

            result_asset: CloudAsset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            structured_data = self._extract_structured_data(stream_asset)
            findings = scan_structured_data_for_pii(structured_data)

            output_file_path = self.create_output_file_path()
            report = {
                "source_pdf": "src/resources/extractPdfInput.pdf",
                "pii_findings_count": len(findings),
                "findings": [asdict(f) for f in findings],
            }
            with open(output_file_path, "w", encoding="utf-8") as out:
                json.dump(report, out, indent=2)

            logging.info("PII scan complete: %d finding(s) written to %s", len(findings), output_file_path)

        except ServiceApiException as e:
            logging.exception("Service API error: %s", e)
        except ServiceUsageException as e:
            logging.exception("Usage/quota error: %s", e)
        except SdkException as e:
            logging.exception("SDK/client error: %s", e)

    @staticmethod
    def _extract_structured_data(stream_asset: StreamAsset) -> dict[str, Any]:
        zip_bytes = stream_asset.get_input_stream()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            with zf.open("structuredData.json") as json_file:
                return json.loads(json_file.read().decode("utf-8"))

    @staticmethod
    def create_output_file_path() -> str:
        now = datetime.now()
        time_stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        os.makedirs("output/ScanPIIFromPDF", exist_ok=True)
        return f"output/ScanPIIFromPDF/pii_report{time_stamp}.json"


if __name__ == "__main__":
    ScanPIIFromPDF()
