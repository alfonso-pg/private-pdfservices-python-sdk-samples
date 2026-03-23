# PII Scan Sample

This sample extracts text and coordinates from a PDF using the Extract PDF operation, then runs a regex-based PII (Personally Identifiable Information) scanner. It detects SSN, email addresses, US phone numbers, credit card numbers, and IBANs, and outputs a JSON report with masked findings and location metadata (page, path, bounds).

## Overview

The sample combines the Adobe PDF Services SDK **Extract PDF** operation with a local PII detection layer. It:

1. Uploads the PDF and runs Extract PDF with text elements and character info
2. Parses the `structuredData.json` from the Extract PDF result
3. Scans each text element with regex patterns for common PII types
4. Writes a timestamped JSON report to `output/PIIScan/` with masked values and location metadata

The report includes `total_findings`, `findings_by_type` (count per PII type), and `findings` (array of objects with `pii_type`, `masked_value`, `page`, `path`, and `bounds`).

## Prerequisites

- **Python**: 3.10 or above
- **Dependencies**: Install via `pip install -r requirements.txt` from the project root
- **Credentials**: Adobe PDF Services API credentials. Create credentials via [Get Started](https://www.adobe.io/apis/documentcloud/dcsdk/gettingstarted.html?ref=getStartedWithServicesSdk).
- **Environment variables**:
  - `PDF_SERVICES_CLIENT_ID` — client ID from `pdfservices-api-credentials.json`
  - `PDF_SERVICES_CLIENT_SECRET` — client secret from `pdfservices-api-credentials.json`

## How to Run

1. Set the environment variables (from the project root):

   ```bash
   export PDF_SERVICES_CLIENT_ID=<YOUR CLIENT ID>
   export PDF_SERVICES_CLIENT_SECRET=<YOUR CLIENT SECRET>
   ```

   On Windows:
   ```bash
   SET PDF_SERVICES_CLIENT_ID=<YOUR CLIENT ID>
   SET PDF_SERVICES_CLIENT_SECRET=<YOUR CLIENT SECRET>
   ```

2. Activate the virtual environment (if used):

   ```bash
   source .venv/bin/activate
   ```

3. Run the sample:

   With the default input (`src/resources/extractPdfInput.pdf`):

   ```bash
   python src/piiscan/scan_pdf_for_pii.py
   ```

   With a custom input file:

   ```bash
   python src/piiscan/scan_pdf_for_pii.py path/to/your.pdf
   ```

4. Check the output in `output/PIIScan/pii_report_<timestamp>.json`.

## Additional Notes

- **PII patterns**: The scanner uses regex patterns for SSN (`XXX-XX-XXXX`), email, US phone, credit card (grouped digits), and IBAN. These are heuristic and may produce false positives or miss variants.
- **Masking**: Reported values are masked for display (e.g. `jo***@example.com`). The original values are never written to the output file.
- **ServiceUsageError**: If you receive this error, your trial credentials may have exhausted the usage quota. Request paid credentials via the [contact form](https://www.adobe.com/go/pdftoolsapi_requestform).
- **Related operations**: See [Extract PDF API documentation](https://developer.adobe.com/document-services/docs/apis/#tag/Extract-PDF) for the underlying operation.
