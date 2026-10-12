"""Finds name, mobile, email, GitHub and LinkedIn in resume text.

Works on the text already extracted from the PDF, so no extra Gemini call is needed.
This is best effort: a value that cannot be found is returned as None.
"""

import re
from typing import Dict, Optional

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# Indian mobile: 10 digits starting with 6-9, with an optional +91 / 91 prefix.
INDIAN_MOBILE_RE = re.compile(r"(?<!\d)(?:\+?91[\s\-]?)?[6-9]\d{4}[\s\-]?\d{5}(?!\d)")
# Any other phone-like number. Checked for 10 to 13 digits below.
GENERIC_PHONE_RE = re.compile(r"(?<!\d)\+?\(?\d[\d\s\-()]{8,18}\d(?!\d)")
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/([A-Za-z0-9][A-Za-z0-9\-]{0,38})", re.IGNORECASE)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:[a-z]{2,3}\.)?linkedin\.com/in/([A-Za-z0-9_%\-]+)", re.IGNORECASE)

# Words that show a line is a heading or a job title, not a person's name.
NOT_NAME_WORDS = {
    "resume", "curriculum", "vitae", "cv", "profile", "summary", "objective",
    "contact", "email", "phone", "mobile", "address", "skills", "experience",
    "education", "projects", "linkedin", "github", "portfolio", "engineer",
    "developer", "intern", "analyst", "manager", "machine", "learning", "data",
    "python", "software",
}


def _find_name(lines) -> Optional[str]:
    for raw in lines[:12]:
        line = raw.strip()
        if not line or len(line) > 40:
            continue
        if re.search(r"[\d@/:|,()\[\]{}]", line):
            continue
        words = line.split()
        if not 2 <= len(words) <= 4:
            continue
        if not all(re.fullmatch(r"[A-Za-z][A-Za-z.'\-]*", w) for w in words):
            continue
        if any(w.lower().strip(".") in NOT_NAME_WORDS for w in words):
            continue
        return line.title() if line.isupper() else line
    return None


def _find_phone(text: str) -> Optional[str]:
    match = INDIAN_MOBILE_RE.search(text)
    if match:
        return re.sub(r"\s+", " ", match.group(0)).strip()
    for match in GENERIC_PHONE_RE.finditer(text):
        digits = re.sub(r"\D", "", match.group(0))
        if 10 <= len(digits) <= 13:
            return re.sub(r"\s+", " ", match.group(0)).strip()
    return None


def extract_contact_details(text: str) -> Dict[str, Optional[str]]:
    text = text or ""
    email = EMAIL_RE.search(text)
    github = GITHUB_RE.search(text)
    linkedin = LINKEDIN_RE.search(text)
    return {
        "full_name": _find_name(text.splitlines()),
        "phone": _find_phone(text),
        "email": email.group(0) if email else None,
        "github": f"https://github.com/{github.group(1)}" if github else None,
        "linkedin": f"https://www.linkedin.com/in/{linkedin.group(1)}" if linkedin else None,
    }