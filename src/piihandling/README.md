# PII handling (Extract PDF + regex scan)

## Overview

This sample uses the [Extract PDF](https://developer.adobe.com/document-services/docs/apis/#tag/Extract-PDF/operation/pdfoperations.extractpdf) operation to extract **text** elements with per-character bounding boxes (`add_char_info=True`), then reads `structuredData.json` from the result zip. It scans that text with configurable regular expressions to flag likely personally identifiable information (PII).

**Note:** Regex-based detection is illustrative only. Production systems require policy, tuning, and often human review.

## Prerequisites

- Python 3.10 or later
- Dependencies from the repository root: `pip install -r requirements.txt`
- Environment variables: `PDF_SERVICES_CLIENT_ID` and `PDF_SERVICES_CLIENT_SECRET` (see the root `README.md`)

## How to Run

From the repository root:

```bash
python src/piihandling/pii_scan_from_extracted_pdf.py
```

By default the sample reads `src/resources/extractPdfInput.pdf`. It writes:

- `output/PiiScanFromExtractedPdf/extract_<timestamp>.zip` — Extract PDF result (includes `structuredData.json`)
- `output/PiiScanFromExtractedPdf/pii_report_<timestamp>.json` — JSON report with `extract_zip`, `finding_count`, and `findings` (masked match strings and PDF bounds where available)

## Additional Notes

- Element structure and fields in `structuredData.json` are described in the [JSON schema for Extract PDF output](https://opensource.adobe.com/pdftools-sdk-docs/release/shared/extractJSONOutputSchema.json).
- Adjust patterns in `DEFAULT_PII_PATTERNS` in `pii_scan_from_extracted_pdf.py` for your use case; avoid logging raw PII in production logs.
