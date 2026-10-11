# AI ATS Resume Checker & Resume Builder

A FastAPI web app with two tools, both powered by Google Gemini:

1. **ATS Resume Checker**: upload a resume PDF and paste a job description. You get an ATS score, strengths, missing keywords, actionable fixes, and a rewritten summary. The report can be downloaded as a PDF.
2. **AI Resume Builder**: fill in your details and get a clean, single-column, ATS-friendly resume. You can preview it, print it, or download it as a formatted PDF.

## Tech Stack

- **Backend:** FastAPI, Uvicorn, Python 3.10+ (3.12 recommended)
- **AI:** Google Gen AI SDK (`google-genai`) with `gemini-3.8-flash`
- **Documents:** pypdf (read PDFs), ReportLab (write PDFs), Markdown
- **Frontend:** Jinja2 templates, Tailwind CSS and Bootstrap via CDN

## Setup

### 1. Get a Gemini API key

Create one at <https://aistudio.google.com/apikey>.

### 2. Create a virtual environment and install dependencies

**Windows (PowerShell):**

```powershell
cd free-ats-chaker
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**macOS / Linux:**

```bash
cd free-ats-chaker
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3. Add your API key

Create a file named `.env` in the project root:

```env
GEMINI_API_KEY=your_api_key_here
```

Optional: pin a specific model with `GEMINI_MODEL=gemini-3.8-flash`.

### 4. Run the app

```bash
uvicorn main:app --reload
```

Open <http://127.0.0.1:8000> in your browser.

- `/` : ATS Resume Checker
- `/resume-builder` : AI Resume Builder

## Configuration

| Variable         | Required | Description |
|------------------|----------|-------------|
| `GEMINI_API_KEY` | Yes      | Your Gemini API key. |
| `GEMINI_MODEL`   | No       | Model to try first. If it is unavailable, the app falls back to `gemini-3.8-flash`, then `gemini-3.6-flash`, then `gemini-3.5-flash-lite`. |
| `GEMINI_THINKING_LEVEL` | No | `low` (default, fastest). Use `medium` for higher quality at the cost of speed. `minimal` is not supported by Gemini 3.8 Flash. |

## Resume Templates

The AI Resume Builder has four ATS-friendly templates. Each one is single-column and text-only, so ATS parsers can read it.

| Template | Look | Best for |
|----------|------|----------|
| Classic  | Times font, centred name, black and white | Corporate, finance, government |
| Modern   | Helvetica, left-aligned name, dark blue accents | Tech and startups (default) |
| Minimal  | Lots of white space, thin grey dividers | Any industry |
| Compact  | Tight spacing so the resume fits on one page | Freshers |

Pick a template before generating. On the result page you can switch templates instantly, without another AI call. Templates are defined in `src/resume_themes.py`.

## Troubleshooting

- **`404 ... model ... is not found / no longer available`**: Google has retired that model. Set `GEMINI_MODEL` to a current model from <https://ai.google.dev/gemini-api/docs/models>, or update `DEFAULT_MODELS` in `src/gemini_client.py`.
- **`GEMINI_API_KEY is missing`**: make sure `.env` is in the project root (next to `main.py`), then restart the server.
- **"PDF appears to be empty or unreadable"**: the PDF has no text layer, usually because it is a scan or a photo. Export a text-based PDF from Word or Google Docs.
- **500 "Internal error" from Gemini**: this is usually temporary. The app retries automatically; try again in a moment.
- **Logs**: each server start writes a timestamped log file to `logs/`.

## Project Structure

```
free-ats-chaker/
├── main.py                 # FastAPI routes
├── src/
│   ├── gemini_client.py    # Gemini SDK wrapper (model fallback, retries)
│   ├── prompts.py          # Prompt builders and output cleanup
│   ├── pdf_builder.py      # Markdown -> formatted PDF (ReportLab)
│   ├── resume_themes.py    # Resume templates (used by both PDF and preview)
│   ├── exception.py        # Custom exception with a user-friendly message
│   └── logger.py           # Log file setup
├── templates/              # Jinja2 HTML pages
├── requirements.txt
└── pyproject.toml
```

## Security Note

Never commit `.env` or share your API key. `.env` is already listed in `.gitignore`. If a key has been shared or uploaded anywhere, rotate it in Google AI Studio and update `.env`.
