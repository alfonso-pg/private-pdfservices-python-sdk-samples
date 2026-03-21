# AGENTS.md

## Cursor Cloud specific instructions

This repository is the **Adobe PDF Services Python SDK Samples** — a collection of ~60 standalone Python scripts demonstrating Adobe PDF Services API operations. There is no web server, no database, no build system, and no automated test suite.

### Environment

- **Python 3.10+** is required. A virtual environment at `.venv/` is used.
- Activate it with `source .venv/bin/activate` before running any sample.
- The sole dependency is `pdfservices-sdk==4.2.0`, installed via `pip install -r requirements.txt`.

### Running samples

- All samples are standalone scripts under `src/`. Run from the repo root, e.g.: `python src/createpdf/create_pdf_from_docx.py`
- Every sample requires the environment variables `PDF_SERVICES_CLIENT_ID` and `PDF_SERVICES_CLIENT_SECRET` to be set with valid Adobe API credentials.
- Samples produce output in an `output/` directory at the repo root.
- See `README.md` for the full list of samples and their invocations.

### Caveats

- There is no linter, formatter, or automated test suite configured in this repo. Validation is done by running sample scripts end-to-end against the Adobe cloud API.
- If you receive a `ServiceUsageError`, the API credentials' trial quota may be exhausted.
- The `python3.12-venv` system package must be installed for `python3 -m venv` to work (already handled in environment setup).
