"""
 Copyright 2024 Adobe
 All Rights Reserved.

 NOTICE: Adobe permits you to use, modify, and distribute this file in
 accordance with the terms of the Adobe license agreement accompanying it.

 This sample extracts text and coordinates from a PDF using the ExtractPDF
 operation, then runs a regex-based PII (Personally Identifiable Information)
 scanner to detect and report findings with page and element context.
"""

import io
import json
import logging
import os
import re
import sys
import zipfile
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import (
    ServiceApiException,
    ServiceUsageException,
    SdkException,
)
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.extract_pdf_job import ExtractPDFJob
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_element_type import ExtractElementType
from adobe.pdfservices.operation.pdfjobs.params.extract_pdf.extract_pdf_params import ExtractPDFParams
from adobe.pdfservices.operation.pdfjobs.result.extract_pdf_result import ExtractPDFResult

logging.basicConfig(level=logging.INFO)

# PII patterns: (name, regex). Order matters for overlapping patterns.
PII_PATTERNS = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")),
    ("us_phone", re.compile(r"\b(?:\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b")),
    ("credit_card", re.compile(r"\b(?:\d{4}[- ]?){3}\d{4}\b")),
    ("iban", re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4,30}\b")),
]


def _mask_value(value: str, show_chars: int = 2) -> str:
    """Mask a PII value for safe display (e.g. jo***@example.com)."""
    if len(value) <= show_chars * 2:
        return "*" * len(value)
    return value[:show_chars] + "*" * (len(value) - show_chars * 2) + value[-show_chars:]


@dataclass
class PIIFinding:
    """A single PII finding with type, masked value, and location."""

    pii_type: str
    masked_value: str
    page: int | None
    path: str | None
    bounds: dict[str, float] | None
    char_start: int | None
    char_end: int | None


@dataclass
class PIIReport:
    """Full PII scan report."""

    input_path: str
    total_findings: int
    findings_by_type: dict[str, int] = field(default_factory=dict)
    findings: list[dict[str, Any]] = field(default_factory=list)


def extract_structured_data(stream_asset: StreamAsset) -> dict:
    """Extract structuredData.json from the ExtractPDF zip output."""
    zip_bytes = stream_asset.get_input_stream()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        with zf.open("structuredData.json") as json_file:
            return json.loads(json_file.read().decode("utf-8"))


def _extract_page_from_path(path: str | None) -> int | None:
    """Extract page number from element path if present (e.g. /report/body/page[1]/para)."""
    if not path:
        return None
    match = re.search(r"page\[?(\d+)\]?", path, re.IGNORECASE)
    return int(match.group(1)) if match else None


def scan_text_for_pii(
    text: str,
    page: int | None = None,
    path: str | None = None,
    bounds: dict | None = None,
) -> list[PIIFinding]:
    """Run regex-based PII scan on text and return findings with location info."""
    findings: list[PIIFinding] = []
    for pii_type, pattern in PII_PATTERNS:
        for match in pattern.finditer(text):
            findings.append(
                PIIFinding(
                    pii_type=pii_type,
                    masked_value=_mask_value(match.group(0)),
                    page=page,
                    path=path,
                    bounds=bounds,
                    char_start=match.start(),
                    char_end=match.end(),
                )
            )
    return findings


def scan_elements_for_pii(data: dict) -> list[PIIFinding]:
    """Walk extracted elements, run PII scan on Text, and collect findings."""
    all_findings: list[PIIFinding] = []
    elements = data.get("elements", [])
    for element in elements:
        text = element.get("Text", "")
        if not text or not isinstance(text, str):
            continue
        path = element.get("Path")
        bounds = element.get("Bounds")
        page = _extract_page_from_path(path)
        if page is None and path:
            page = _extract_page_from_path(str(path))
        findings = scan_text_for_pii(text=text, page=page, path=path, bounds=bounds)
        all_findings.extend(findings)
    return all_findings


def build_report(findings: list[PIIFinding], input_path: str) -> PIIReport:
    """Build a PIIReport from findings."""
    by_type: dict[str, int] = {}
    for f in findings:
        by_type[f.pii_type] = by_type.get(f.pii_type, 0) + 1
    findings_dicts = [
        {
            "pii_type": f.pii_type,
            "masked_value": f.masked_value,
            "page": f.page,
            "path": f.path,
            "bounds": f.bounds,
        }
        for f in findings
    ]
    return PIIReport(
        input_path=input_path,
        total_findings=len(findings),
        findings_by_type=by_type,
        findings=findings_dicts,
    )


class ScanPDFForPII:
    """
    Extracts text and coordinates from a PDF using ExtractPDF, then scans
    for PII using regex patterns. Outputs a JSON report of findings.
    """

    DEFAULT_INPUT = "src/resources/extractPdfInput.pdf"

    def __init__(self, input_path: str | None = None):
        path = input_path or self.DEFAULT_INPUT
        try:
            with open(path, "rb") as file:
                input_stream = file.read()

            credentials = ServicePrincipalCredentials(
                client_id=os.getenv("PDF_SERVICES_CLIENT_ID"),
                client_secret=os.getenv("PDF_SERVICES_CLIENT_SECRET"),
            )

            pdf_services = PDFServices(credentials=credentials)
            input_asset = pdf_services.upload(
                input_stream=input_stream, mime_type=PDFServicesMediaType.PDF
            )

            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[ExtractElementType.TEXT],
                add_char_info=True,
            )

            extract_pdf_job = ExtractPDFJob(
                input_asset=input_asset, extract_pdf_params=extract_pdf_params
            )

            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(
                location, ExtractPDFResult
            )

            result_asset: CloudAsset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            structured_data = extract_structured_data(stream_asset)
            findings = scan_elements_for_pii(structured_data)
            report = build_report(findings, path)

            output_path = self._create_output_path()
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "input_path": report.input_path,
                        "total_findings": report.total_findings,
                        "findings_by_type": report.findings_by_type,
                        "findings": report.findings,
                    },
                    f,
                    indent=2,
                )

            logging.info(
                "PII scan complete: %d finding(s) -> %s",
                report.total_findings,
                output_path,
            )

        except FileNotFoundError as e:
            logging.exception("Input file not found: %s", e)
            sys.exit(1)
        except ServiceApiException as e:
            logging.exception("Service API error: %s", e)
        except ServiceUsageException as e:
            logging.exception("Usage/quota error: %s", e)
        except SdkException as e:
            logging.exception("SDK/client error: %s", e)

    @staticmethod
    def _create_output_path() -> str:
        now = datetime.now()
        time_stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        os.makedirs("output/PIIScan", exist_ok=True)
        return f"output/PIIScan/pii_report_{time_stamp}.json"


if __name__ == "__main__":
    input_file = sys.argv[1] if len(sys.argv) > 1 else None
    ScanPDFForPII(input_path=input_file)
