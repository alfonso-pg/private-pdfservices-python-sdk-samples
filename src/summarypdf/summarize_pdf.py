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
    """Extract text from a PDF and generate a JSON summary."""

    def __init__(self):
        """
        Execute the PDF summarization workflow.

        Inputs:
            No direct parameters. Reads `src/resources/extractPdfInput.pdf` and
            the credentials from environment variables.
        Outputs:
            Writes a JSON summary file to `output/SummarizePDF/`.
        """
        input_file_path = "src/resources/extractPdfInput.pdf"
        try:
            logging.info("Reading input PDF from %s", input_file_path)
            with open(input_file_path, "rb") as input_file:
                input_stream = input_file.read()

            credentials = ServicePrincipalCredentials(
                client_id=os.getenv('PDF_SERVICES_CLIENT_ID'),
                client_secret=os.getenv('PDF_SERVICES_CLIENT_SECRET')
            )

            pdf_services = PDFServices(credentials=credentials)

            logging.info("Uploading input PDF to PDF Services")
            input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)

            extract_pdf_params = ExtractPDFParams(
                elements_to_extract=[ExtractElementType.TEXT],
            )

            extract_pdf_job = ExtractPDFJob(input_asset=input_asset, extract_pdf_params=extract_pdf_params)

            logging.info("Submitting Extract PDF job")
            location = pdf_services.submit(extract_pdf_job)
            pdf_services_response = pdf_services.get_job_result(location, ExtractPDFResult)

            result_asset: CloudAsset = pdf_services_response.get_result().get_resource()
            stream_asset: StreamAsset = pdf_services.get_content(result_asset)

            structured_data = self._extract_structured_data(stream_asset)
            document_text = self._collect_text(structured_data)
            summary = self._summarize_with_llm(document_text)

            output_file_path = self.create_output_file_path()
            logging.info("Writing summary JSON to %s", output_file_path)
            with open(output_file_path, "w", encoding="utf-8") as output_file:
                json.dump(summary, output_file, indent=2)

            logging.info(f"Summary written to {output_file_path}")

        except FileNotFoundError as e:
            logging.exception("Input PDF file not found: %s", e)
        except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, ValueError) as e:
            logging.exception("I/O or parsing error encountered: %s", e)
        except (ServiceApiException, ServiceUsageException, SdkException) as e:
            logging.exception(f'Exception encountered while executing operation: {e}')

    @staticmethod
    def _extract_structured_data(stream_asset: StreamAsset) -> dict:
        """
        Read and parse extracted JSON data from SDK ZIP output.

        Inputs:
            stream_asset: Extract operation result stream containing ZIP bytes.
        Outputs:
            A dictionary parsed from `structuredData.json`.
        """
        zip_bytes = stream_asset.get_input_stream()
        logging.info("Reading structuredData.json from extracted ZIP")
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_file:
            with zip_file.open("structuredData.json") as json_file:
                return json.loads(json_file.read())

    @staticmethod
    def _collect_text(data: dict) -> str:
        """
        Concatenate extracted text elements into a single string.

        Inputs:
            data: Parsed JSON dictionary from `structuredData.json`.
        Outputs:
            A single string containing extracted text, truncated if too long.
        """
        parts = []
        for element in data.get("elements", []):
            element_text = element.get("Text", "")
            if element_text:
                parts.append(element_text)
        full_text = "\n".join(parts)
        logging.info("Collected %d text elements from extracted data", len(parts))
        if not full_text:
            logging.warning("No extractable text elements found in structured data.")
        if len(full_text) > MAX_TEXT_LENGTH:
            full_text = full_text[:MAX_TEXT_LENGTH]
            logging.warning("Document text truncated to %d characters for LLM input.", MAX_TEXT_LENGTH)
        return full_text

    @staticmethod
    def _summarize_with_llm(document_text: str) -> dict:
        """
        Generate a structured summary from extracted PDF text.

        Inputs:
            document_text: Extracted text content to summarize.
        Outputs:
            A dictionary with summary fields returned by the LLM.
        """
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required.")

        client = OpenAI(api_key=openai_api_key)
        logging.info("Requesting summary from OpenAI model gpt-4.1-mini")

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

        response_content = response.choices[0].message.content
        if not response_content:
            raise ValueError("OpenAI response did not include summary content.")

        return json.loads(response_content)

    @staticmethod
    def create_output_file_path() -> str:
        """
        Build the output path for the summary JSON file.

        Inputs:
            No direct parameters.
        Outputs:
            A timestamped output file path under `output/SummarizePDF/`.
        """
        now = datetime.now()
        time_stamp = now.strftime("%Y-%m-%dT%H-%M-%S")
        os.makedirs("output/SummarizePDF", exist_ok=True)
        return f"output/SummarizePDF/summary{time_stamp}.json"


if __name__ == "__main__":
    SummarizePDF()
