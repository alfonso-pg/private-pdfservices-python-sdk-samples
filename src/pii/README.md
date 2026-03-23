# Scan a PDF for PII (regex)

## Overview

This sample demonstrates how to combine the **Extract PDF** operation with local pattern matching. It extracts text elements with **per-character bounding boxes** (`add_char_info=True`), reads `structuredData.json` from the Extract API result ZIP, applies regular-expression rules to each text element, and writes a JSON report of potential PII matches—including **page number** and **PDF user-space bounds** for each match when character bounds are available.

The sample is intended as a starting point for redaction workflows, compliance checks, or downstream automation. Regex rules are illustrative only; tune them for your jurisdiction and acceptable false-positive rate.

## Prerequisites

- **Python**: 3.10 or later (see the [Python downloads](https://www.python.org/downloads/) page).
- **Dependencies**: Install from the repository root using `requirements.txt` (includes `pdfservices-sdk`).
- **Credentials**: A PDF Services **client ID** and **client secret** from the Adobe Developer Console (same as other samples in this project).
- **Environment variables** (required):
  - `PDF_SERVICES_CLIENT_ID`
  - `PDF_SERVICES_CLIENT_SECRET`

For credential setup, see **Authentication Setup** in the [repository README](../../README.md).

**Input file**: The script uses `src/resources/extractPdfInput.pdf` (bundled with the samples). No command-line arguments are required.

## How to Run

Run all commands from the **repository root** (the directory that contains `requirements.txt` and `src/`).

1. Create and activate a virtual environment (recommended), then install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. Set your PDF Services credentials:

   ```bash
   export PDF_SERVICES_CLIENT_ID=<YOUR CLIENT ID>
   export PDF_SERVICES_CLIENT_SECRET=<YOUR CLIENT SECRET>
   ```

   On Windows (Command Prompt):

   ```bat
   SET PDF_SERVICES_CLIENT_ID=<YOUR CLIENT ID>
   SET PDF_SERVICES_CLIENT_SECRET=<YOUR CLIENT SECRET>
   ```

3. Execute the sample:

   ```bash
   python src/pii/scan_pii_from_pdf.py
   ```

## Additional notes

- **Output**: Reports are written to `output/ScanPIIFromPDF/` as `pii_report<timestamp>.json` (ISO-like local timestamp in the filename). Each file includes `source_pdf`, `pii_findings_count`, and a `findings` array with `pii_type`, `matched_text`, `page`, `path`, `bounds`, `char_start`, and `char_end`.
- **Extract PDF**: The operation and ZIP layout (including `structuredData.json`) are described in the [Adobe PDF Services API documentation](https://developer.adobe.com/document-services/docs/apis/#tag/Extract-PDF). Character-level bounds enable mapping matches back to coordinates in the PDF.
- **Patterns**: Default patterns in the script cover common shapes (for example email-like strings, US phone and SSN formats, 16-digit card-like sequences). Replace or extend `DEFAULT_PII_PATTERNS` for production use.
- **Quota**: If you see a usage or quota error from the API, your trial limits may be exhausted. See **Quota Exhaustion** in the [repository README](../../README.md).
