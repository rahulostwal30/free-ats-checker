import html
import io
import os
import re
import sys
from typing import Optional

import markdown
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape
from pypdf import PdfReader

from src.contacts import clean_contact, save_contact
from src.exception import CustomException
from src.gemini_client import generate_text
from src.logger import logging
from src.pdf_builder import markdown_to_pdf_bytes
from src.prompts import build_ats_analysis_prompt, build_resume_prompt, clean_model_markdown
from src.resume_themes import DEFAULT_THEME, get_theme, theme_choices, theme_css

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
MAX_UPLOAD_BYTES = 5 * 1024 * 1024  # 5 MB

app = FastAPI(title="AI ATS Resume Checker & Builder")
templates_env = Environment(
    loader=FileSystemLoader(TEMPLATE_DIR),
    autoescape=select_autoescape(["html"]),
)


def render(template_name: str, **context) -> HTMLResponse:
    template = templates_env.get_template(template_name)
    return HTMLResponse(content=template.render(**context))


def error_page(request: Request, message: str, status_code: int) -> HTMLResponse:
    return HTMLResponse(
        content=templates_env.get_template("error.html").render(
            request=request, error_message=message
        ),
        status_code=status_code,
    )


def store_contact(source: str, contact: dict) -> None:
    """Save the contact details, but never block the result if saving fails."""
    try:
        save_contact(source, contact)
    except Exception as e:
        # Log only the error type: some database error messages include the values.
        logging.error(f"Could not save contact from {source}: {type(e).__name__}")


def pdf_response(pdf_bytes: bytes, filename: str) -> Response:
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def extract_pdf_text(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    text = "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    if not text:
        raise ValueError("The uploaded PDF appears to be empty or unreadable. Scanned PDFs are not supported.")
    return text


def markdown_to_html(markdown_text: str) -> str:
    return markdown.markdown(html.escape(markdown_text or "", quote=False), extensions=["extra"])


def safe_filename_part(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name or "").strip("_")


def render_resume_page(
    request: Request,
    resume_markdown: str,
    full_name: str,
    job_title: str,
    email: str,
    phone: str,
    template_key: str,
) -> HTMLResponse:
    theme = get_theme(template_key)
    return render(
        "builder_result.html",
        request=request,
        result=markdown_to_html(resume_markdown),
        resume_markdown=resume_markdown,
        full_name=(full_name or "").strip(),
        job_title=(job_title or "").strip(),
        email=(email or "").strip(),
        phone=(phone or "").strip(),
        theme_key=theme.key,
        themes=theme_choices(),
    )


@app.get("/theme-css/{template_key}")
async def theme_stylesheet(template_key: str):
    return Response(content=theme_css(get_theme(template_key)), media_type="text/css")


@app.exception_handler(CustomException)
async def custom_exception_handler(request: Request, exc: CustomException):
    logging.error(f"Handling custom exception: {exc}")
    return HTMLResponse(
        content=templates_env.get_template("error.html").render(
            {"request": request, "error_message": exc.user_message}
        ),
        status_code=500,
    )


# --- ATS CHECKER ROUTES ---

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    try:
        logging.info("Home page accessed.")
        return render("index.html", request=request)
    except Exception as e:
        logging.error(f"Error loading home page: {e}")
        raise CustomException(e, sys)


@app.post("/analyze", response_class=HTMLResponse)
async def analyze_resume(
    request: Request,
    job_description: str = Form(...),
    resume: UploadFile = File(...),
    full_name: str = Form(""),
    phone: str = Form(""),
    email: str = Form(""),
    github: str = Form(""),
    linkedin: str = Form(""),
    consent: Optional[str] = Form(None),
):
    logging.info("Analyzing a resume upload.")
    try:
        contact = clean_contact(full_name, phone, email, github, linkedin, consent)

        filename = resume.filename or ""
        if not filename.lower().endswith(".pdf"):
            raise ValueError("Invalid file format. Please upload a PDF resume.")

        content = await resume.read()
        if len(content) > MAX_UPLOAD_BYTES:
            raise ValueError("The PDF is too large. Please upload a file under 5 MB.")

        resume_text = extract_pdf_text(content)
        analysis_markdown = clean_model_markdown(
            generate_text(build_ats_analysis_prompt(resume_text, job_description))
        )
        store_contact("ats_check", contact)

        return render(
            "result.html",
            request=request,
            result=markdown_to_html(analysis_markdown),
            analysis_markdown=analysis_markdown,
        )
    except ValueError as ve:
        logging.warning(f"Validation failed: {ve}")
        return error_page(request, str(ve), 400)
    except Exception as e:
        logging.error(f"Error during resume analysis: {e}")
        raise CustomException(e, sys)


@app.post("/download-pdf")
async def download_pdf(analysis_markdown: str = Form(...)):
    try:
        pdf_bytes = markdown_to_pdf_bytes(
            analysis_markdown,
            document_title="ATS Analysis Report",
            header_title="AI ATS Resume Analysis Report",
            header_note="Generated by Free AI ATS Resume Checker",
        )
        return pdf_response(pdf_bytes, "ATS_Analysis_Report.pdf")
    except Exception as e:
        logging.error(f"Error generating analysis PDF: {e}")
        raise CustomException(e, sys)


# --- AI RESUME BUILDER ROUTES ---

@app.get("/resume-builder", response_class=HTMLResponse)
async def resume_builder_page(request: Request):
    try:
        logging.info("Resume Builder page accessed.")
        return render(
            "builder.html",
            request=request,
            themes=theme_choices(),
            default_theme=DEFAULT_THEME,
        )
    except Exception as e:
        logging.error(f"Error loading resume builder page: {e}")
        raise CustomException(e, sys)


@app.post("/generate-resume", response_class=HTMLResponse)
async def generate_resume(
    request: Request,
    full_name: str = Form(...),
    job_title: str = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    linkedin: Optional[str] = Form(None),
    github: Optional[str] = Form(None),
    education: str = Form(...),
    experience: str = Form(...),
    projects: str = Form(...),
    skills: str = Form(...),
    template: str = Form(DEFAULT_THEME),
    consent: Optional[str] = Form(None),
):
    logging.info(f"Generating resume with template {template}")
    try:
        contact = clean_contact(full_name, phone, email, github or "", linkedin or "", consent)
        details = {
            "full_name": full_name,
            "job_title": job_title,
            "email": email,
            "phone": phone,
            "linkedin": linkedin,
            "github": github,
            "education": education,
            "experience": experience,
            "projects": projects,
            "skills": skills,
        }
        resume_markdown = clean_model_markdown(generate_text(build_resume_prompt(details)))
        store_contact("resume_builder", contact)

        return render_resume_page(
            request, resume_markdown, full_name, job_title, email, phone, template,
        )
    except ValueError as ve:
        logging.warning(f"Validation failed: {ve}")
        return error_page(request, str(ve), 400)
    except Exception as e:
        logging.error(f"Failed to generate resume via Gemini API: {e}")
        raise CustomException(e, sys)


@app.post("/preview-template", response_class=HTMLResponse)
async def preview_template(
    request: Request,
    resume_markdown: str = Form(...),
    full_name: str = Form(""),
    job_title: str = Form(""),
    email: str = Form(""),
    phone: str = Form(""),
    template: str = Form(DEFAULT_THEME),
):
    try:
        logging.info(f"Switching resume template to {template}")
        return render_resume_page(
            request, resume_markdown, full_name, job_title, email, phone, template,
        )
    except Exception as e:
        logging.error(f"Error switching resume template: {e}")
        raise CustomException(e, sys)


@app.post("/download-built-resume")
async def download_built_resume(
    resume_markdown: str = Form(...),
    full_name: str = Form(""),
    template: str = Form(DEFAULT_THEME),
):
    try:
        theme = get_theme(template)
        name_part = safe_filename_part(full_name)
        filename = f"{name_part}_Resume.pdf" if name_part else "ATS_Optimized_Resume.pdf"
        pdf_bytes = markdown_to_pdf_bytes(
            resume_markdown,
            document_title=f"{full_name.strip()} - Resume" if full_name.strip() else "Resume",
            theme_key=theme.key,
        )
        return pdf_response(pdf_bytes, filename)
    except Exception as e:
        logging.error(f"Error downloading built resume PDF: {e}")
        raise CustomException(e, sys)