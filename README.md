# LifeAdmin — AI Life Admin & Document Intelligence Hub

A polished, local-first personal document workspace built with Python and Flask. LifeAdmin helps people organize important paperwork, search extracted text, review key dates and amounts, and ask questions grounded in their own indexed files.

> **Privacy note:** This project is designed for local use. Uploaded originals and extracted text remain in the configured data directory unless you explicitly configure a remote AI provider. This initial release does not encrypt uploaded files at application level; use a private device account and full-disk encryption.

## Highlights

- **Modern responsive dashboard** with document metrics, attention queue, category distribution, and an AI-style document query surface.
- **Document vault** for PDF, common image, TXT, and Markdown uploads, with category filtering and full-text search.
- **Local extraction** for text and PDFs; optional OCR for scans using Tesseract + Pillow + pytesseract.
- **Metadata suggestions** for document category, dates, bill amount, summary, and keyword tags. Review all extracted fields.
- **Document Q&A** with local retrieval and an extractive answer fallback. An OpenAI-compatible endpoint is optional and disabled unless explicitly configured.
- **Deadline intelligence** for expiry dates and payment due dates, surfaced on the overview.
- **PII pattern scanner** flags likely email, phone, ID-like, and IBAN-like strings with masked previews.
- **Editable document records**, original-file download, deletion, JSON dashboard API, and automated tests.

## Quick start

Python 3.10+ recommended.

```bash
python -m venv .venv
# macOS / Linux
source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000 in your browser. The app binds to localhost by default.

## OCR setup

For scanned PDFs and image files, install the Tesseract system application for your OS. Python dependencies for OCR are listed in `requirements.txt`. PDF text extraction uses pypdf; image OCR requires the Tesseract executable to be available on PATH. Without these, files are still stored but may have no searchable text.

## Optional AI provider

Leave these variables unset to keep document Q&A local and extractive. To use an OpenAI-compatible endpoint, set:

```bash
AI_BASE_URL=https://your-provider.example/v1
AI_API_KEY=your-key
AI_MODEL=your-model
```

The app sends only retrieved excerpts for a question to the configured provider. Do not enable remote AI for sensitive documents unless you understand and accept the provider's data handling terms. Use environment variables; never commit API keys.

## Data & safety

- By default, the database and original files live in `data/`, which is excluded from Git.
- Set `LIFE_ADMIN_DATA` to choose a private data directory.
- Maximum upload size is configurable with `MAX_UPLOAD_MB` (default 20).
- PII scanning is heuristic and may miss sensitive values or produce false positives.
- Metadata extraction is heuristic. Always verify critical dates, amounts, and identifiers against the source.
- This app is a personal organizer, not legal, medical, financial, or emergency advice.
- Do not expose the development server to the public internet. If adding multi-user access, authentication, encryption, and threat modeling are required.

## Tests

```bash
python -m pytest -q
```

GitHub Actions runs the test suite on pushes to `main` and pull requests.

## Project structure

```text
.
├── app.py
├── intelligence.py
├── templates/
│   ├── base.html
│   ├── dashboard.html
│   ├── documents.html
│   ├── detail.html
│   ├── answer.html
│   └── privacy.html
├── static/
│   ├── style.css
│   └── app.js
└── tests/
```

## Roadmap

- Encrypted vault and protected backup/restore
- Better multilingual OCR and robust locale-aware date/amount extraction
- Embeddings-backed semantic retrieval
- Calendar integrations and native notifications
- Batch import, duplicate detection, and export bundles
- Secure redaction of original PDF/image files
- Accessibility refinements and localization

## License

MIT
