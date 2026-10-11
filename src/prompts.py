"""Prompt builders and output cleanup helpers.

These are plain Python functions with no web or SDK imports, so they can be
reused and tested on their own.
"""

import re
from typing import Dict

BLANK = "(blank)"


def _or_blank(value: str) -> str:
    value = (value or "").strip()
    return value if value else BLANK


def build_ats_analysis_prompt(resume_text: str, job_description: str) -> str:
    return f"""You are an expert HR ATS system. Analyze this resume against the given job description.

Resume content:
{resume_text}

Job description:
{job_description}

Provide the output in strict markdown with exactly these sections, in this order:
## ATS Score: [X]/100
### 3 Strengths
### 3 Missing Keywords & Failures
### Actionable Suggestions to Fix
### Re-written ATS Friendly Summary
"""


def build_resume_prompt(details: Dict[str, str]) -> str:
    """Build the prompt that turns raw form input into a clean ATS resume.

    Empty fields are passed as (blank) so the model leaves them out instead of
    copying a placeholder into the resume. User free-text fields are passed as
    clearly delimited data blocks, so multi-line input stays intact.
    """
    full_name = _or_blank(details.get("full_name"))
    job_title = _or_blank(details.get("job_title"))
    email = _or_blank(details.get("email"))
    phone = _or_blank(details.get("phone"))
    linkedin = _or_blank(details.get("linkedin"))
    github = _or_blank(details.get("github"))
    education = _or_blank(details.get("education"))
    skills = _or_blank(details.get("skills"))
    experience = _or_blank(details.get("experience"))
    projects = _or_blank(details.get("projects"))

    return f"""You are an expert resume writer and ATS (Applicant Tracking System) specialist.

Write a complete, ATS-friendly resume in Markdown using ONLY the candidate details below.

OUTPUT RULES
- Output the resume only. No introduction, no notes, no explanations, no code fences.
- Use exactly this structure, in this order:
  # <Full Name>
  ### <Target Job Title>
  **Email:** <email> | **Phone:** <phone> | **LinkedIn:** <url> | **GitHub:** <url>
  ## PROFESSIONAL SUMMARY
  Three concise sentences tailored to the target job title and skills. No first-person pronouns.
  ## CORE SKILLS
  One line of skills separated by " | ".
  ## WORK EXPERIENCE
  One block per role: "### <Role> | <Company> | <Duration>" followed by 2 to 4 bullets.
  ## KEY PROJECTS
  One block per project: "### <Project name> | <Technologies used>" followed by 2 to 3 bullets.
  ## EDUCATION
  One line per entry: "### <Degree>, <Institution> | <Year>".
- BLANK VALUES: a value shown as (blank) must be left out completely. Never write "(blank)", "Not provided", "Not mentioned", "N/A", or empty brackets in the resume. Examples:
  - If a job has no duration, the heading is "### <Role> | <Company>".
  - If LinkedIn is (blank), leave the LinkedIn item out of the contact line.
  - If work experience is (blank), leave out the whole WORK EXPERIENCE section.
- SPELLING AND CAPITALISATION: fix obvious spelling mistakes. Capitalise names, job titles, degrees, companies and technologies properly. For example, "senior" becomes "Senior" and "bechlor" becomes "Bachelor".
- Every bullet is a Markdown bullet ("- ") that starts with a strong action verb.
- Use only facts from the details. Do NOT invent employers, job titles, dates, metrics, certifications, or technologies. If a bullet would need a number that was not given, describe the outcome without a number.
- Turn rough notes into clean, professional sentences of 25 words or fewer.
- Plain text only: no tables, no columns, no images, no emojis.

CANDIDATE DETAILS
Full name: {full_name}
Target job title: {job_title}
Email: {email}
Phone: {phone}
LinkedIn: {linkedin}
GitHub / Portfolio: {github}
Education: {education}
Skills: {skills}

Work experience / background (raw notes):
<<<
{experience}
>>>

Key projects (raw notes):
<<<
{projects}
>>>
"""


_HEADING_LINE = re.compile(r"^\s*#{1,6}\s")
_CONTACT_LABEL = re.compile(r"^\s*\*\*(Email|Phone|LinkedIn|GitHub)\b", re.IGNORECASE)
_PLACEHOLDER = re.compile(r"not provided|not mentioned|\bn/a\b|\(blank\)", re.IGNORECASE)


def _should_scrub(line: str) -> bool:
    """Only resume headings (they use " | " between parts) and the resume
    contact line are cleaned. Analysis report lines are never touched."""
    if _HEADING_LINE.match(line):
        return "|" in line
    return bool(_CONTACT_LABEL.match(line))


def _scrub_placeholder_line(line: str) -> str:
    """Remove placeholder wording from a heading or contact line.

    Parts separated by " | " are dropped if they contain a placeholder. Inside
    a part, comma-separated pieces are dropped the same way, so
    "Degree, Institution Not Provided | Year Not Provided" keeps only "Degree".
    """
    if not _PLACEHOLDER.search(line):
        return line

    kept_segments = []
    for segment in line.split("|"):
        if not _PLACEHOLDER.search(segment):
            kept_segments.append(segment.strip())
            continue
        chunks = [chunk.strip() for chunk in segment.split(",")]
        chunks = [chunk for chunk in chunks if chunk and not _PLACEHOLDER.search(chunk)]
        if chunks:
            kept_segments.append(", ".join(chunks))
    return " | ".join(segment for segment in kept_segments if segment)


def clean_model_markdown(text: str) -> str:
    """Remove code fences, chatty preamble, and placeholder wording the model may add."""
    cleaned = (text or "").strip()

    # If the model wrapped the document in a code fence, keep only the fenced
    # content and drop anything written before or after it.
    fenced = re.search(r"```[a-zA-Z]*[ \t]*\n(.*?)```", cleaned, re.DOTALL)
    if fenced and fenced.group(1).strip():
        cleaned = fenced.group(1).strip()

    lines = cleaned.splitlines()
    start = 0
    for index, line in enumerate(lines):
        if _HEADING_LINE.match(line):
            start = index
            break

    result = []
    for line in lines[start:]:
        if _should_scrub(line):
            line = _scrub_placeholder_line(line)
            if not line.strip("#* \t"):
                continue
        result.append(line)
    return "\n".join(result).strip()