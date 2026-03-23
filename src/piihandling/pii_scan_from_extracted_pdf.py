"""
 Copyright 2025 Adobe
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
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Iterator

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
class PIIPattern:
    """A demonstrative regex label and pattern. Tune for your compliance needs."""

    label: str
    pattern: re.Pattern


# Default patterns are illustrative only; not a substitute for legal/compliance review.
DEFAULT_PII_PATTERNS: list[PIIPattern] = [
    PIIPattern("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")),
    PIIPattern(
        "us_phone",
        re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b"),
    ),
    PIIPattern("ssn_like", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    PIIPattern(
        "credit_card_like",
        re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
    ),
]


def _mask_value(value: str, keep_prefix: int = 2) -> str:
    if len(value) <= keep_prefix:
        return "***"
    return value[:keep_prefix] + "***"


def _normalize_bounds(bounds: Any) -> dict[str, float | None] | None:
    if not isinstance(bounds, dict):
        return None
    return {
        "left": bounds.get("Left") if "Left" in bounds else bounds.get("left"),
        "top": bounds.get("Top") if "Top" in bounds else bounds.get("top"),
        "right": bounds.get("Right") if "Right" in bounds else bounds.get("right"),
        "bottom": bounds.get("Bottom") if "Bottom" in bounds else bounds.get("bottom"),
    }


def _iter_text_elements(node: Any) -> Iterator[dict[str, Any]]:
    """Walk Extract JSON (structuredData.json) and yield dicts that carry Text content."""
    if isinstance(node, dict):
        text = node.get("Text")
        if isinstance(text, str) and text.strip():
            yield node
        for child in node.values():
            yield from _iter_text_elements(child)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_text_elements(item)


def _read_structured_data_from_zip(zip_bytes: bytes) -> dict[str, Any]:
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        json_name = None
        for name in zf.namelist():
            if name.rstrip("/").endswith("structuredData.json"):
                json_name = name
                break
        if not json_name:
            raise FileNotFoundError("structuredData.json not found in extract result zip")
        raw = zf.read(json_name)
    return json.loads(raw.decode("utf-8"))


def _bounds_for_span(
    text: str,
    start: int,
    end: int,
    element: dict[str, Any],
) -> dict[str, float | None] | None:
    """
    If per-character bounds are present (Extract with add_char_info), approximate bounds for [start:end).
    Otherwise fall back to the element's Bounds.
    """
    chars = element.get("Chars") or element.get("chars")
    if isinstance(chars, list) and len(chars) == len(text) and end > start:
        span_boxes: list[dict[str, float | None]] = []
        for i in range(start, min(end, len(chars))):
            ch = chars[i]
            if isinstance(ch, dict):
                b = _normalize_bounds(ch.get("Bounds") or ch.get("bounds"))
                if b:
                    span_boxes.append(b)
        if span_boxes:
            lefts = [x["left"] for x in span_boxes if x.get("left") is not None]
            rights = [x["right"] for x in span_boxes if x.get("right") is not None]
            bottoms = [x["bottom"] for x in span_boxes if x.get("bottom") is not None]
            tops = [x["top"] for x in span_boxes if x.get("top") is not None]
            if lefts and rights and bottoms and tops:
                return {
                    "left": min(lefts),
                    "right": max(rights),
                    "bottom": min(bottoms),
                    "top": max(tops),
                }
    return _normalize_bounds(element.get("Bounds") or element.get("bounds"))


def scan_text_for_pii(
    patterns: list[PIIPattern],
    structured: dict[str, Any],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for element in _iter_text_elements(structured):
        text = element["Text"]
        path = element.get("Path")
        page = element.get("PageNumber")
        if page is None:
            page = element.get("Page")
        for pii in patterns:
            for m in pii.pattern.finditer(text):
                bounds = _bounds_for_span(text, m.start(), m.end(), element)
                findings.append(
                    {
                        "pii_type": pii.label,
                        "match_masked": _mask_value(m.group(0)),
                        "span": {"start": m.start(), "end": m.end()},
                        "path": path,
                        "page": page,
                        "bounds_pdf": bounds,
                    }
                )
    return findings


@dataclass
class PiiScanFromExtractedPdf:
    """Extract PDF text (with character bounds), then run regex-based PII detection on structuredData.json."""

    input_pdf_path: str = "src/resources/extractPdfInput.pdf"
    patterns: list[PIIPattern] = field(default_factory=lambda: list(DEFAULT_PII_PATTERNS))

    def run(self) -> str | None:
        try:
            with open(self.input_pdf_path, "rb") as file:
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
            raw_stream = stream_asset.get_input_stream()
            if isinstance(raw_stream, (bytes, bytearray)):
                zip_bytes = bytes(raw_stream)
            else:
                zip_bytes = raw_stream.read()

            structured = _read_structured_data_from_zip(zip_bytes)
            findings = scan_text_for_pii(self.patterns, structured)

            zip_path = self._write_extract_zip(zip_bytes)
            report_path = self._write_report(findings, zip_path)

            logging.info("Extract zip saved to: %s", zip_path)
            logging.info("PII scan report: %s (%d finding(s))", report_path, len(findings))
            for item in findings:
                logging.info(
                    "PII [%s] page=%s path=%s bounds=%s",
                    item["pii_type"],
                    item.get("page"),
                    item.get("path"),
                    item.get("bounds_pdf"),
                )
            return report_path

        except ServiceApiException as e:
            logging.exception("Service API error: %s", e)
        except ServiceUsageException as e:
            logging.exception("Usage/quota error: %s", e)
        except SdkException as e:
            logging.exception("SDK/client error: %s", e)
        except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as e:
            logging.exception("Failed to parse extract result or write output: %s", e)
        return None

    def _write_extract_zip(self, zip_bytes: bytes) -> str:
        out_dir = "output/PiiScanFromExtractedPdf"
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        path = f"{out_dir}/extract_{ts}.zip"
        with open(path, "wb") as f:
            f.write(zip_bytes)
        return path

    def _write_report(self, findings: list[dict[str, Any]], extract_zip_path: str) -> str:
        out_dir = "output/PiiScanFromExtractedPdf"
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y-%m-%dT%H-%M-%S")
        path = f"{out_dir}/pii_report_{ts}.json"
        payload = {
            "extract_zip": extract_zip_path,
            "finding_count": len(findings),
            "findings": findings,
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return path


if __name__ == "__main__":
    PiiScanFromExtractedPdf().run()
