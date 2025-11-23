import re
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import random

# configure module logger
logger = logging.getLogger("hireflow.backend")
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(logging.INFO)


# Mock external services (replace with real integrations as needed)
class CalendarAPI:
    @staticmethod
    def fetch_availability(preferred_date: str) -> List[str]:
        try:
            base_date = datetime.strptime(preferred_date, "%Y-%m-%d")
        except Exception:
            base_date = datetime.utcnow()
        slots = [
            (base_date + timedelta(hours=9)).strftime("%Y-%m-%dT%H:%M:%S"),
            (base_date + timedelta(hours=11)).strftime("%Y-%m-%dT%H:%M:%S"),
            (base_date + timedelta(hours=14)).strftime("%Y-%m-%dT%H:%M:%S"),
        ]
        logger.info("Fetched availability for %s -> %s", preferred_date, slots)
        return slots

    @staticmethod
    def create_event(candidate_name: str, candidate_email: str, slot: str) -> str:
        link = f"https://calendar.example.com/event/{candidate_name.replace(' ', '_')}/{slot}"
        logger.info("Created calendar event: %s", link)
        return link


class EmailService:
    @staticmethod
    def send_email(to_email: str, subject: str, body: str) -> bool:
        logger.info("Mock send email to %s subject=%s", to_email, subject)
        return True


class SlackService:
    @staticmethod
    def send_message(channel: str, message: str) -> bool:
        logger.info("Mock slack message to %s: %s", channel, message)
        return True


class ATSDatabase:
    _db: Dict[str, Any] = {}

    @classmethod
    def upsert_candidate(cls, candidate_data: Dict[str, Any]) -> str:
        candidate_id = candidate_data.get("email") or f"id_{random.randint(1000,9999)}"
        cls._db[candidate_id] = candidate_data
        logger.info("Upserted ATS candidate %s", candidate_id)
        return "success"


# Utilities
def validate_email(email: str) -> bool:
    if not email:
        return False
    pattern = r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    return re.match(pattern, email) is not None


def validate_phone(phone: str) -> bool:
    if not phone:
        return False
    pattern = r"^\+?[0-9\s\-()]{7,20}$"
    return re.match(pattern, phone) is not None


def sanitize_phone(phone: str) -> str:
    if not phone:
        return ""
    return re.sub(r"[^0-9+]+", "", phone)


def extract_skills(resume_text: str, skill_set: Optional[List[str]] = None) -> List[str]:
    if not resume_text:
        return []
    if skill_set is None:
        skill_set = [
            "python", "java", "c++", "javascript", "react", "nodejs", "aws", "docker",
            "kubernetes", "sql", "nosql", "machine learning", "nlp", "deep learning",
            "cloud", "devops", "agile", "scrum", "git"
        ]
    synonyms = {
        "nodejs": ["node", "node.js", "nodejs"],
        "javascript": ["js", "javascript"],
        "c++": ["c++", "cpp"],
        "machine learning": ["machine learning", "ml"],
        "deep learning": ["deep learning", "dl"],
    }
    found_skills = set()
    text_lower = resume_text.lower()
    for skill in skill_set:
        patterns = synonyms.get(skill, [skill])
        for p in patterns:
            if '+' in p:
                if p in text_lower:
                    found_skills.add(skill)
            else:
                if re.search(rf"\b{re.escape(p)}\b", text_lower):
                    found_skills.add(skill)
    logger.info("Extracted skills: %s", found_skills)
    return sorted(found_skills)


def extract_experience_years(resume_text: str) -> float:
    if not resume_text:
        return 0.0
    matches = re.findall(r"(\d+(?:\.\d+)?)(?:\+)?\s*(?:years|yrs|y)\b", resume_text.lower())
    years = [float(m[0]) for m in matches]
    if years:
        return max(years)
    # fallback: 0
    return 0.0


def extract_education(resume_text: str) -> str:
    if not resume_text:
        return "Not specified"
    edu_keywords = ["phd", "doctorate", "master", "bachelor", "associate", "diploma", "high school"]
    lines = resume_text.splitlines()
    for line in lines:
        lower = line.lower()
        for kw in edu_keywords:
            if kw in lower:
                return line.strip()
    return "Not specified"


def extract_work_history(resume_text: str) -> List[Dict[str, Any]]:
    history: List[Dict[str, Any]] = []
    pattern = r"(?P<title>[\w\s]+)\s+at\s+(?P<company>[\w\s]+)\s+\((?P<start>\d{4})-(?P<end>\d{4}|present)\)"
    matches = re.finditer(pattern, resume_text, re.IGNORECASE)
    for m in matches:
        history.append({
            "title": m.group("title").strip(),
            "company": m.group("company").strip(),
            "start_year": m.group("start"),
            "end_year": m.group("end"),
        })
    logger.info("Extracted work history entries: %d", len(history))
    return history


def generate_summary(parsed_data: Dict[str, Any]) -> str:
    summary = (
        f"{parsed_data.get('name','Unknown')} has {parsed_data.get('experience_years',0)} years of experience "
        f"with skills in {', '.join(parsed_data.get('skills',[]))}. "
        f"Education: {parsed_data.get('education','Not specified')}."
    )
    return summary


# Core components
def parse_resume(resume_text: str) -> Dict[str, Any]:
    email_candidates = re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", resume_text)
    phone_candidates = re.findall(r"\+?\d[\d\s\-]{7,}\d", resume_text)
    email = next((e for e in email_candidates if validate_email(e)), "")
    phone = next((p for p in phone_candidates if validate_phone(p)), "")
    phone = sanitize_phone(phone)

    # Robust name extraction:
    # 1. Look for a line starting with 'Name' (case-insensitive) and take until end-of-line
    # 2. Look for common labels like 'Candidate' or 'Full Name'
    # 3. Fallback: first non-empty line that doesn't look like a label (not email/phone/experience/education)
    name = "Unknown"
    lines = [ln.strip() for ln in resume_text.splitlines()]
    for ln in lines:
        if not ln:
            continue
        m = re.match(r"^(?:name|full name|candidate)[:\-\s]+(.+)$", ln, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            break
    if name == "Unknown":
        # fallback: find first line that is not an email or phone or a short label
        for ln in lines:
            if not ln:
                continue
            lower = ln.lower()
            if re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", ln):
                continue
            if re.search(r"\+?\d[\d\s\-]{6,}", ln):
                continue
            if any(k in lower for k in ("experience", "education", "skills", "work history", "workhistory", "summary")):
                continue
            # likely a name
            # trim common labels like 'name' if present
            ln2 = re.sub(r"^name[:\-\s]+", "", ln, flags=re.IGNORECASE).strip()
            if 1 <= len(ln2) <= 80:
                name = ln2
                break

    skills = extract_skills(resume_text)
    experience_years = extract_experience_years(resume_text)
    education = extract_education(resume_text)
    work_history = extract_work_history(resume_text)

    summary = generate_summary({
        "name": name,
        "skills": skills,
        "experience_years": experience_years,
        "education": education,
    })

    parsed = {
        "name": name,
        "email": email,
        "phone": phone,
        "skills": skills,
        "experience_years": experience_years,
        "education": education,
        "work_history": work_history,
        "summary": summary,
    }
    logger.info("Parsed resume: %s", {"name": name, "email": email})
    return parsed


def score_candidate(parsed_resume: Dict[str, Any], job_requirements: Dict[str, Any]) -> Dict[str, Any]:
    candidate_skills = set(parsed_resume.get("skills", []))
    required_skills = set(job_requirements.get("skills", []))
    skill_match_ratio = len(candidate_skills.intersection(required_skills)) / max(len(required_skills), 1)

    candidate_exp = parsed_resume.get("experience_years", 0.0)
    exp_required = job_requirements.get("min_experience", 0)
    experience_match_ratio = min(candidate_exp / exp_required if exp_required > 0 else 1.0, 1.0)

    education = parsed_resume.get("education", "").lower()
    education_required = job_requirements.get("education_level", "").lower()

    education_rank = {
        "high school": 1,
        "diploma": 2,
        "associate": 3,
        "bachelor": 4,
        "master": 5,
        "phd": 6,
        "doctorate": 6
    }
    candidate_edu_score = 0
    required_edu_score = education_rank.get(education_required, 0)
    for edu_key, rank in education_rank.items():
        if edu_key in education:
            candidate_edu_score = rank
            break
    education_match_ratio = candidate_edu_score / required_edu_score if required_edu_score > 0 else 1.0
    education_match_ratio = min(education_match_ratio, 1.0)

    score = round(100 * (0.4 * skill_match_ratio + 0.4 * experience_match_ratio + 0.2 * education_match_ratio), 2)

    explanation = (
        f"Skill Match: {skill_match_ratio*100:.1f}%, Experience Match: {experience_match_ratio*100:.1f}%, "
        f"Education Match: {education_match_ratio*100:.1f}%. Final score weighted accordingly."
    )

    result = {
        "score": score,
        "skill_match": round(skill_match_ratio * 100, 2),
        "experience_match": round(experience_match_ratio * 100, 2),
        "explanation": explanation,
    }
    logger.info("Scored candidate %s -> %s", parsed_resume.get('name'), result['score'])
    return result


def schedule_interview(candidate_name: str, candidate_email: str, preferred_date: str) -> Dict[str, Any]:
    available_slots = CalendarAPI.fetch_availability(preferred_date)
    confirmed_slot = available_slots[0] if available_slots else "No slots available"
    calendar_event_link = ""
    if confirmed_slot != "No slots available":
        calendar_event_link = CalendarAPI.create_event(candidate_name, candidate_email, confirmed_slot)
        EmailService.send_email(
            candidate_email,
            "Interview Scheduled",
            f"Dear {candidate_name}, your interview is scheduled at {confirmed_slot}. Link: {calendar_event_link}"
        )
    return {"confirmed_slot": confirmed_slot, "calendar_event_link": calendar_event_link}


def notify_hr(message: str) -> Dict[str, Any]:
    slack_status = SlackService.send_message("#hr-channel", message)
    email_status = EmailService.send_email("hr@example.com", "Notification from HireFlow AI", message)
    status = "success" if slack_status and email_status else "failure"
    logger.info("Notify HR status=%s message=%s", status, message)
    return {"status": status}


def update_ats(candidate_data: Dict[str, Any]) -> Dict[str, Any]:
    status = ATSDatabase.upsert_candidate(candidate_data)
    return {"status": status}


def send_decision_email(candidate_email: str, candidate_name: str, decision: str, role: Optional[str] = None, custom_message: Optional[str] = None) -> Dict[str, Any]:
    """Send an acceptance or rejection email to the candidate.

    decision: 'accept' or 'reject'
    role: optional role/title
    custom_message: optional body to include
    """
    try:
        if not candidate_email or not validate_email(candidate_email):
            raise ValueError("Invalid candidate email")

        decision_lower = (decision or '').strip().lower()
        if decision_lower not in ('accept', 'reject'):
            raise ValueError('decision must be "accept" or "reject"')

        subject = ''
        body_lines = []
        if decision_lower == 'accept':
            subject = f"Application update: {role or 'Application'} - Interview Invitation"
            body_lines.append(f"Dear {candidate_name or 'Candidate'},")
            body_lines.append("")
            body_lines.append("Congratulations — we've reviewed your application and would like to move forward with an interview.")
            if role:
                body_lines.append(f"Role: {role}")
            body_lines.append("")
            body_lines.append("Please reply with your availability, or use the link provided in a follow-up email to pick a slot.")
        else:
            subject = f"Application update: {role or 'Application'} - Decision"
            body_lines.append(f"Dear {candidate_name or 'Candidate'},")
            body_lines.append("")
            body_lines.append("Thank you for your interest and the time you invested in applying. After careful consideration, we will not be moving forward with your application at this time.")
            body_lines.append("")
            body_lines.append("We appreciate your interest and encourage you to apply for other roles in the future.")

        if custom_message:
            body_lines.append("")
            body_lines.append(custom_message)

        body_lines.append("")
        body_lines.append("Best regards,")
        body_lines.append("Hiring Team")

        body = "\n".join(body_lines)
        sent = EmailService.send_email(candidate_email, subject, body)
        logger.info("Decision email sent to %s decision=%s role=%s status=%s", candidate_email, decision_lower, role, sent)
        return {"status": "sent" if sent else "failed"}
    except Exception as e:
        logger.exception("Failed to send decision email")
        return {"status": "error", "error": str(e)}


def on_resume_submit(resume_text: str, job_requirements: Dict[str, Any], preferred_interview_date: str) -> Dict[str, Any]:
    parsed = parse_resume(resume_text)
    scored = score_candidate(parsed, job_requirements)

    workflow_log: Dict[str, Any] = {"parsed_resume": parsed, "score_result": scored, "actions": []}

    if scored["score"] >= 60:
        interview_info = schedule_interview(parsed["name"], parsed["email"], preferred_interview_date)
        workflow_log["actions"].append({"action": "schedule_interview", "details": interview_info})
    else:
        notify_result = notify_hr(f"Candidate {parsed['name']} scored below threshold with score {scored['score']}.")
        workflow_log["actions"].append({"action": "notify_hr", "details": notify_result})
    ats_result = update_ats(parsed)
    workflow_log["actions"].append({"action": "update_ats", "details": ats_result})

    final_notify = notify_hr("Candidate processing completed.")
    workflow_log["actions"].append({"action": "notify_hr", "details": final_notify})

    return workflow_log

def validate_date_str(date_str: str) -> bool:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except Exception:
        return False


def process_workflow(resume_text: str, job_requirements: Dict[str, Any], preferred_interview_date: str) -> Dict[str, Any]:
    try:
        if preferred_interview_date and not validate_date_str(preferred_interview_date):
            raise ValueError("preferred_interview_date must be YYYY-MM-DD")
        result = on_resume_submit(resume_text, job_requirements, preferred_interview_date)
        logger.info("Workflow completed: score=%s", result.get('score_result', {}).get('score'))
        return {"ok": True, "workflow": result}
    except Exception as e:
        logger.exception("Workflow processing failed")
        return {"ok": False, "error": str(e)}


def generate_ai_response(message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Simple simulated AI responder for demo purposes.
    Uses heuristics to answer common recruitment questions and can reference parsed resume data from context.
    """
    if not message:
        return {"response": "Please provide a question or command."}

    msg = message.lower()
    # If context contains a parsed resume, allow queries about it
    parsed = context.get('parsed_resume') if context else None

    if 'summar' in msg and parsed:
        return {"response": parsed.get('summary', 'No summary available.')}

    if 'skills' in msg and parsed:
        return {"response": 'Skills found: ' + (', '.join(parsed.get('skills', [])) or 'None')}

    if 'score' in msg and parsed:
        # quick simulated scoring
        score_info = score_candidate(parsed, context.get('job_requirements', {})) if context else {'score': 50}
        return {"response": f"Estimated score: {score_info.get('score')}%. Details: {score_info.get('explanation', '')}", "score": score_info}

    if 'schedule' in msg:
        # suggest available slots for given date in message or default to today
        import re
        m = re.search(r"(\d{4}-\d{2}-\d{2})", message)
        date = m.group(1) if m else datetime.utcnow().strftime('%Y-%m-%d')
        slots = CalendarAPI.fetch_availability(date)
        return {"response": f"Available slots on {date}: {', '.join(slots)}", "slots": slots}

    # default echo plus minor enhancement
    return {"response": f"I understood: '{message}'. For deeper analysis, include a resume or ask to 'summarize' or 'score' a candidate."}

