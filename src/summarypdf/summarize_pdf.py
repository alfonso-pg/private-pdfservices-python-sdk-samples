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
import zipfile
from datetime import datetime

from openai import OpenAI

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

MAX_TEXT_LENGTH = 100_000


#
# This sample illustrates how to extract content from a PDF and produce an
# LLM-based summary using OpenAI's gpt-4.1-mini model.
#
# Refer to README.md for instructions on how to run the samples.
#
class SummarizePDF:
    """Extract PDF text and write an LLM-generated JSON summary to disk."""

    def __init__(self):
        """Run the end-to-end summarize flow from input PDF to output JSON file."""
        try:
            input_pdf_path = "src/resources/extractPdfInput.pdf"
            logging.info("Reading input PDF from %s", input_pdf_path)
            with open(input_pdf_path, "rb") as input_file:
                input_stream = input_file.read()

            credentials = ServicePrincipalCredentials(
                client_id=os.getenv('PDF_SERVICES_CLIENT_ID'),
                client_secret=os.getenv('PDF_SERVICES_CLIENT_SECRET')
            )

            pdf_services = PDFServices(credentials=credentials)

            logging.info("Uploading PDF and starting Extract PDF job")
            input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)

            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[ExtractElementType.TEXT],
            )

            extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)

            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)

            result_asset: CloudAsset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            logging.info("Extracting structured JSON result")
            structured_data = self._extract_structured_data(stream_asset)
            document_text = self._collect_text(structured_data)
            logging.info("Generating summary with LLM")
            summary = self._summarize_with_llm(document_text)

            output_file_path = self.create_output_file_path()
            logging.info("Writing summary output to %s", output_file_path)
            with open(output_file_path, "w", encoding="utf-8") as output_file:
                json.dump(summary, output_file, indent=2)

            logging.info("Summary written to %s", output_file_path)

        except (ServiceApiException, ServiceUsageException, SdkException) as exc:
            logging.exception("Exception encountered while executing PDF operation: %s", exc)
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValueError) as exc:
            logging.exception("Exception encountered while processing input/output data: %s", exc)

    @staticmethod
    def _extract_structured_data(stream_asset: StreamAsset) -> dict:
        """Return extracted structured JSON payload from the SDK zip result."""
        zip_bytes = stream_asset.get_input_stream()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            with zf.open("structuredData.json") as json_file:
                return json.loads(json_file.read())

    @staticmethod
    def _collect_text(data: dict) -> str:
        """Build a single text string from extracted elements.

        Args:
            data: Parsed JSON dictionary from Extract PDF output.

        Returns:
            A newline-delimited text string, truncated to MAX_TEXT_LENGTH.
        """
        parts = []
        for element in data.get("elements", []):
            text = element.get("Text", "")
            if text:
                parts.append(text)
        full_text = "\n".join(parts)
        if len(full_text) > MAX_TEXT_LENGTH:
            full_text = full_text[:MAX_TEXT_LENGTH]
            logging.warning("Document text truncated to %d characters for LLM input.", MAX_TEXT_LENGTH)
        return full_text

    @staticmethod
    def _summarize_with_llm(document_text: str) -> dict:
        """Summarize extracted text with OpenAI and return structured JSON.

        Args:
            document_text: The extracted document text used as LLM input.

        Returns:
            A dictionary containing title, summary, key_topics, and word_count.
        """
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        response = client.chat.completions.create(
            model="gpt-4.1-mini",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a document summarisation assistant. "
                        "Given the full text of a PDF document, produce a JSON object with these keys:\n"
                        "  - \"title\": the inferred title of the document (string)\n"
                        "  - \"summary\": a concise 3-5 sentence summary of the content (string)\n"
                        "  - \"key_topics\": a list of up to 5 main topics covered (list of strings)\n"
                        "  - \"word_count\": total number of words in the provided text (integer)\n"
                        "Return ONLY valid JSON with no extra text."
                    ),
                },
                {
                    "role": "user",
                    "content": document_text,
                },
            ],
            temperature=0.2,
            response_format={"type": "json_object"},
        )

        return json.loads(response.choices[0].message.content)

    @staticmethod
    def create_output_file_path() -> str:
        """Create and return the timestamped output path for the summary JSON file."""
        now = datetime.now()
        time_stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        os.makedirs("output/SummarizePDF", exist_ok=True)
        return f"output/SummarizePDF/summary{time_stamp}.json"


if __name__ == "__main__":
    SummarizePDF()
