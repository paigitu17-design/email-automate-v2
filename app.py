import json
import os
import re
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd
from flask import Flask, flash, jsonify, redirect, render_template, request, send_file, url_for
from openai import OpenAI, OpenAIError
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from werkzeug.utils import secure_filename

from parse_excel import extract_contacts_from_file


BASE_DIR = Path(__file__).resolve().parent

# Auto-load API key from config/ folder
CONFIG_DIR = BASE_DIR / "config"
KEY_FILE = CONFIG_DIR / "openai_key.txt"
CONFIG_ENV = CONFIG_DIR / ".env"

if KEY_FILE.exists():
    key = KEY_FILE.read_text(encoding="utf-8").strip()
    if key:
        os.environ["OPENAI_API_KEY"] = key
elif CONFIG_ENV.exists():
    with open(CONFIG_ENV, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip().strip('"').strip("'")

DATA_DIR = BASE_DIR / "data"
WORKBOOK_PATH = DATA_DIR / "enriched_contacts.xlsx"
ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

BASE_COLUMNS = [
    "Bank Name",
    "Person Name",
    "Designation",
    "Email",
    "LinkedIn",
    "Confidence Score",
    "Email Status",
    "LinkedIn Status",
    "Email Sent",
    "LinkedIn Contacted",
    "Remarks",
]
EXTRA_COLUMNS = [
    "Approved",
    "Generated Email Subject",
    "Generated Email Body",
    "Generated Connection Request",
    "Generated Intro Message",
    "Generated Follow-Up Message",
]
ALL_COLUMNS = BASE_COLUMNS + EXTRA_COLUMNS
REQUIRED_INPUT_COLUMNS = ["Bank Name", "Person Name", "Designation"]
REQUIRED_ROLES = [
    "CEO",
    "CFO",
    "COO",
    "CRO (Chief Risk Officer)",
    "CTO / CIO",
    "CAO (Chief Audit Officer)",
    "Head of Data",
    "Head of Compliance",
    "Financial Controller / CAO",
]
ROLE_ALIASES = {
    "CEO": ["CEO", "CHIEF EXECUTIVE OFFICER"],
    "CFO": ["CFO", "CHIEF FINANCIAL OFFICER"],
    "COO": ["COO", "CHIEF OPERATING OFFICER"],
    "CRO (Chief Risk Officer)": ["CRO", "CHIEF RISK OFFICER", "CRO (CHIEF RISK OFFICER)"],
    "CTO / CIO": ["CTO", "CIO", "CHIEF TECHNOLOGY OFFICER", "CHIEF INFORMATION OFFICER",
                  "CHIEF DIGITAL OFFICER", "CTO / CIO"],
    "CAO (Chief Audit Officer)": ["CAO", "CHIEF AUDIT OFFICER", "HEAD OF INTERNAL AUDIT",
                                  "CHIEF INTERNAL AUDITOR", "CAO (CHIEF AUDIT OFFICER)"],
    "Head of Data": ["HEAD OF DATA", "DATA DIRECTOR", "CHIEF DATA OFFICER", "CDO",
                     "CHIEF AI OFFICER", "CHIEF DATA & AI OFFICER"],
    "Head of Compliance": ["HEAD OF COMPLIANCE", "CHIEF COMPLIANCE OFFICER", "CCO",
                           "HEAD OF COMPLIANCE"],
    "Financial Controller / CAO": ["FINANCIAL CONTROLLER", "CHIEF ACCOUNTING OFFICER",
                                   "FINANCIAL CONTROLLER / CAO"],
}

app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY", "local-contact-tool")
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
DATA_DIR.mkdir(exist_ok=True)


def empty_dataframe():
    return pd.DataFrame(columns=ALL_COLUMNS)


def clean_value(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def read_contacts():
    if not WORKBOOK_PATH.exists():
        return empty_dataframe()
    frame = pd.read_excel(WORKBOOK_PATH, engine="openpyxl", dtype=object)
    for column in ALL_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""
    return frame[ALL_COLUMNS].fillna("")


def save_contacts(frame):
    DATA_DIR.mkdir(exist_ok=True)
    frame = frame.reindex(columns=ALL_COLUMNS, fill_value="")
    with tempfile.NamedTemporaryFile(
        dir=DATA_DIR, suffix=".xlsx", delete=False
    ) as temporary_file:
        temporary_path = Path(temporary_file.name)
    try:
        frame.to_excel(temporary_path, index=False, engine="openpyxl")
        workbook = load_workbook(temporary_path)
        worksheet = workbook.active
        worksheet.freeze_panes = "A2"
        worksheet.auto_filter.ref = worksheet.dimensions
        for cell in worksheet[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="183B56")
            cell.alignment = Alignment(vertical="center")
        for column_cells in worksheet.columns:
            letter = column_cells[0].column_letter
            width = max(
                (len(str(cell.value or "")) for cell in column_cells[:100]),
                default=12,
            )
            worksheet.column_dimensions[letter].width = min(max(width + 2, 12), 42)
        workbook.save(temporary_path)
        os.replace(temporary_path, WORKBOOK_PATH)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def contact_record(row, index):
    record = {column: clean_value(row.get(column, "")) for column in ALL_COLUMNS}
    try:
        score = float(record["Confidence Score"])
        record["Confidence Score"] = int(score) if score.is_integer() else score
    except (TypeError, ValueError):
        record["Confidence Score"] = ""
    record["Approved"] = record["Approved"].lower() in {"yes", "true", "1"}
    record["Email Sent"] = record["Email Sent"].lower() in {"yes", "true", "1"}
    record["LinkedIn Contacted"] = record["LinkedIn Contacted"].lower() in {
        "yes",
        "true",
        "1",
    }
    record["id"] = index
    return record


def get_records(frame=None):
    frame = read_contacts() if frame is None else frame
    return [contact_record(row, index) for index, row in frame.iterrows()]


def coverage_for(records):
    banks = {}
    for record in records:
        bank = record["Bank Name"]
        if not bank:
            continue
        banks.setdefault(bank, set())
        designation = record["Designation"].upper()
        for role, aliases in ROLE_ALIASES.items():
            if any(
                re.search(r"(?<![A-Z])" + re.escape(alias) + r"(?![A-Z])", designation)
                for alias in aliases
            ):
                banks[bank].add(role)
    result = []
    for bank, found in sorted(banks.items(), key=lambda item: item[0].casefold()):
        percentage = round(100 * len(found) / len(REQUIRED_ROLES))
        color = "green" if percentage > 80 else "amber" if percentage > 50 else "red"
        result.append(
            {
                "bank": bank,
                "found": sorted(found, key=REQUIRED_ROLES.index),
                "count": len(found),
                "total": len(REQUIRED_ROLES),
                "percentage": percentage,
                "color": color,
                "missing": [role for role in REQUIRED_ROLES if role not in found],
            }
        )
    return result


def dashboard_stats(records):
    total = len(records)
    emails = sum(bool(record["Email"]) for record in records)
    linkedins = sum(bool(record["LinkedIn"]) for record in records)
    return {
        "total_contacts": total,
        "total_banks": len({r["Bank Name"].casefold() for r in records if r["Bank Name"]}),
        "emails_found": emails,
        "linkedin_found": linkedins,
        "missing_emails": total - emails,
        "missing_linkedin": total - linkedins,
        "emails_generated": sum(bool(r["Generated Email Subject"]) for r in records),
        "linkedin_messages_generated": sum(
            bool(r["Generated Connection Request"] or r["Generated Intro Message"])
            for r in records
        ),
        "approved_contacts": sum(r["Approved"] for r in records),
        "emails_sent": sum(r["Email Sent"] for r in records),
        "linkedin_contacted": sum(r["LinkedIn Contacted"] for r in records),
        "contact_coverage": round(100 * (emails + linkedins) / (2 * total)) if total else 0,
    }


def openai_client():
    key = os.environ.get("OPENAI_API_KEY")
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
        if key:
            os.environ["OPENAI_API_KEY"] = key
    if not key:
        raise RuntimeError("OpenAI API key not found in config/ folder.")
    return OpenAI(api_key=key)


def response_text(response):
    text = getattr(response, "output_text", "")
    if not text:
        raise ValueError("The AI response did not contain usable text. Please try again.")
    return text.strip()


def validate_linkedin_url(value):
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("LinkedIn URL must be a complete http:// or https:// URL.")
    if parsed.netloc.lower() not in {"linkedin.com", "www.linkedin.com"}:
        raise ValueError("Please enter a linkedin.com profile URL.")
    return value


def contact_index(index):
    frame = read_contacts()
    if index < 0 or index >= len(frame):
        return None, None
    return frame, frame.index[index]


@app.get("/")
def index():
    records = get_records()
    return render_template(
        "index.html",
        stats=dashboard_stats(records),
        coverage=coverage_for(records),
        has_contacts=bool(records),
    )


@app.post("/upload")
def upload():
    uploaded_file = request.files.get("file")
    if not uploaded_file or not uploaded_file.filename:
        flash("Choose an Excel file to upload.", "danger")
        return redirect(url_for("index"))
    suffix = Path(secure_filename(uploaded_file.filename)).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        flash("Upload an .xlsx or .xls file.", "danger")
        return redirect(url_for("index"))
    try:
        imported = extract_contacts_from_file(uploaded_file)
        if imported.empty:
            flash("No contacts could be extracted from this Excel file.", "warning")
            return redirect(url_for("index"))
        save_contacts(imported)
        flash(f"Successfully imported {len(imported)} contacts with full details!", "success")
    except Exception as exc:
        flash(f"Could not process Excel file: {exc}", "danger")
    return redirect(url_for("index"))


@app.get("/api/contacts")
def api_contacts():
    records = get_records()
    return jsonify(
        contacts=records,
        stats=dashboard_stats(records),
        coverage=coverage_for(records),
    )


@app.put("/api/contacts/<int:index>")
def update_contact(index):
    frame, row_index = contact_index(index)
    if frame is None:
        return jsonify(error="Contact not found."), 404
    payload = request.get_json(silent=True) or {}
    editable = {
        "Bank Name",
        "Person Name",
        "Designation",
        "Email",
        "LinkedIn",
        "Email Status",
        "LinkedIn Status",
        "Remarks",
    }
    try:
        for column in editable & payload.keys():
            value = str(payload[column] or "").strip()
            if column == "LinkedIn":
                value = validate_linkedin_url(value)
            if column == "Email" and value:
                email_list = [e.strip() for e in value.replace(";", ",").split(",") if e.strip()]
                for em in email_list:
                    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", em):
                        raise ValueError(f"'{em}' is not a valid email address.")
                value = ", ".join(email_list)
            frame.at[row_index, column] = value
        for column in ("Approved", "Email Sent", "LinkedIn Contacted"):
            if column in payload:
                frame.at[row_index, column] = "Yes" if payload[column] else "No"
        save_contacts(frame)
    except ValueError as exc:
        return jsonify(error=str(exc)), 400
    return jsonify(contact=contact_record(frame.loc[row_index], index))


@app.post("/api/contacts/<int:index>/discover")
def discover_contact(index):
    frame, row_index = contact_index(index)
    if frame is None:
        return jsonify(error="Contact not found."), 404
    row = frame.loc[row_index]
    prompt = (
        "Use web search to find publicly listed professional contact details for this "
        "person. Only return an email address or LinkedIn profile URL when supported "
        "by a credible public search result. Never infer or invent an address or URL. "
        "Do not search for private/personal contact details. If not found, use empty "
        "strings. Return ONLY valid JSON with keys email (string), linkedin (string), "
        "confidence_score (integer 0-100), and sources (array of URLs). "
        f"Bank: {clean_value(row['Bank Name'])}; "
        f"Name: {clean_value(row['Person Name'])}; "
        f"Designation: {clean_value(row['Designation'])}."
    )
    try:
        client = openai_client()
        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            tools=[{"type": "web_search_preview"}],
            input=prompt,
        )
        result = json.loads(response_text(response))
        email = clean_value(result.get("email"))
        linkedin = validate_linkedin_url(clean_value(result.get("linkedin")))
        if email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
            email = ""
        try:
            confidence = max(0, min(100, int(result.get("confidence_score", 0))))
        except (ValueError, TypeError):
            confidence = 0
        sources = result.get("sources", [])
        if not isinstance(sources, list):
            sources = []
        source_text = ", ".join(str(source) for source in sources[:5])
        notes = "AI discovery suggestion; verify independently before use."
        if source_text:
            notes += " Sources: " + source_text
        if email:
            frame.at[row_index, "Email"] = email
            frame.at[row_index, "Email Status"] = "Needs review"
        elif not clean_value(row["Email"]):
            frame.at[row_index, "Email Status"] = "Not found"
        if linkedin:
            frame.at[row_index, "LinkedIn"] = linkedin
            frame.at[row_index, "LinkedIn Status"] = "Needs review"
        elif not clean_value(row["LinkedIn"]):
            frame.at[row_index, "LinkedIn Status"] = "Not found"
        frame.at[row_index, "Confidence Score"] = confidence
        frame.at[row_index, "Remarks"] = notes
        save_contacts(frame)
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except OpenAIError as exc:
        return jsonify(error=f"OpenAI request failed: {exc}"), 502
    except (ValueError, json.JSONDecodeError) as exc:
        return jsonify(error=f"Could not use the discovery result: {exc}"), 502
    return jsonify(contact=contact_record(frame.loc[row_index], index))


def build_fallback_email(name, designation, bank):
    subject = f"Strengthening Regulatory Data & Governance at {bank}"
    body = (
        f"Dear {name},\n\n"
        "I am reaching out from Amanah Data Solutions, a UAE-based regulatory data solutions and governance consultancy headquartered in Masdar City, Abu Dhabi. We partner with financial institutions across the UAE and GCC to build trusted data foundations, automate regulatory reporting, and implement robust BCBS 239-aligned data governance frameworks.\n\n"
        f"Following {bank}'s recent growth and digital transformation milestones, financial institutions in your segment face increasingly stringent Central Bank of the UAE (CBUAE) regulatory reporting demands. In your role as {designation}, maintaining end-to-end data lineage across core banking platforms, eliminating legacy data silos, and ensuring data quality for regulatory risk reporting can place significant operational strain on internal teams.\n\n"
        "Amanah Data Solutions addresses these challenges by delivering tailored, end-to-end regulatory data architectures. We help banks automate their regulatory reporting pipelines, implement automated data quality controls, and establish BCBS 239-compliant governance models that turn compliance data into actionable, strategic insights for executive decision-making.\n\n"
        f"I would welcome the opportunity to connect for a brief 20-minute introductory call or demo to share relevant industry benchmarks and conduct a complimentary Data & Regulatory Assessment for {bank}, with zero obligation. Would you be open to a brief conversation this week or next?\n\n"
        "Warm regards,\n\n"
        "Amanah Data Solutions Team\n"
        "Masdar City Free Zone, Abu Dhabi, UAE\n"
        "www.amanahdatasolutions.com | info@amanahdatasolutions.com"
    )
    return subject, body


def build_fallback_linkedin(name, designation, bank):
    return {
        "connection_request": f"Hi {name}, hope you're well. Connecting regarding data governance and regulatory reporting initiatives at {bank}. Best regards from Amanah Data Solutions (Masdar City).",
        "intro_message": (
            f"Dear {name},\n\n"
            f"I am reaching out from Amanah Data Solutions (Abu Dhabi). We help UAE financial institutions automate regulatory reporting and achieve BCBS 239 alignment. Given your leadership as {designation} at {bank}, I would welcome the opportunity to share our framework and offer your team a complimentary 20-minute Data & Regulatory Assessment.\n\n"
            "Would you be open to a brief discussion this week?\n\n"
            "Best regards,\n"
            "Amanah Data Solutions"
        ),
        "follow_up_message": (
            f"Hi {name}, following up on my previous note. Would you have 15-20 minutes next week to discuss data governance and CBUAE compliance readiness at {bank}? Happy to share our complimentary data assessment framework.\n\n"
            "Warm regards,\n"
            "Amanah Data Solutions"
        ),
    }


@app.post("/api/contacts/<int:index>/generate-email")
def generate_email(index):
    frame, row_index = contact_index(index)
    if frame is None:
        return jsonify(error="Contact not found."), 404
    row = frame.loc[row_index]
    person_name = clean_value(row['Person Name']) or "Executive"
    designation = clean_value(row['Designation']) or "Executive Leadership"
    bank_name = clean_value(row['Bank Name']) or "your institution"

    prompt = (
        "Write a highly professional, consultative first-contact B2B email from Amanah Data Solutions "
        f"to {person_name}, {designation} at {bank_name}. "
        "The email body MUST strictly follow this 4-paragraph structure:\n\n"
        "Paragraph 1 - Who Amanah Data Solutions are: Introduce Amanah Data Solutions as a UAE-based regulatory data solutions and governance consultancy (based in Masdar City, Abu Dhabi) specializing in trusted data foundations, automated regulatory reporting, and BCBS 239 alignment for UAE and GCC financial institutions.\n\n"
        f"Paragraph 2 - Research about {bank_name} and potential challenges: Address their bank and their specific role ({designation}), focusing on common challenges such as Central Bank of the UAE (CBUAE) regulatory reporting burdens, data quality inconsistencies across core and legacy banking systems, fragmented data lineage, or scaling data & AI initiatives safely.\n\n"
        "Paragraph 3 - What solutions Amanah Data Solutions provides: Highlight how Amanah Data Solutions solves these pain points through automated regulatory reporting pipelines, BCBS 239-aligned data governance and data quality frameworks, and technology enablement that converts regulatory compliance data into strategic executive insights.\n\n"
        "Paragraph 4 - Call to Action (Free call/demo): Invite them to a brief 20-minute call or demo to conduct a complimentary, zero-obligation Data & Regulatory Assessment for their bank.\n\n"
        f"Subject line: 'Data Governance & Regulatory Reporting for {bank_name}' or 'Strengthening Regulatory Data Readiness at {bank_name}'. "
        "Tone: Senior, executive, consultative, concise. Return ONLY valid JSON with keys 'subject' and 'body'."
    )
    try:
        client = openai_client()
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        generated = json.loads(content)
        subject = clean_value(generated.get("subject"))
        body = clean_value(generated.get("body"))
        if not subject or not body:
            raise ValueError("Incomplete generated email.")
    except Exception:
        # Fallback ensures 100% reliability even if OpenAI account is out of credits
        subject, body = build_fallback_email(person_name, designation, bank_name)

    frame.at[row_index, "Generated Email Subject"] = subject
    frame.at[row_index, "Generated Email Body"] = body
    save_contacts(frame)
    return jsonify(subject=subject, body=body, email=clean_value(row["Email"]))


@app.post("/api/contacts/<int:index>/generate-linkedin")
def generate_linkedin(index):
    frame, row_index = contact_index(index)
    if frame is None:
        return jsonify(error="Contact not found."), 404
    row = frame.loc[row_index]
    person_name = clean_value(row['Person Name']) or "Executive"
    designation = clean_value(row['Designation']) or "Executive Leadership"
    bank_name = clean_value(row['Bank Name']) or "your institution"

    prompt = (
        "Write three concise, professional LinkedIn outreach messages from Amanah Data Solutions "
        f"to {person_name}, {designation} at {bank_name}: "
        "1. connection_request (strictly under 300 characters): Warm, professional note mentioning their role at their bank and connecting on data governance/regulatory reporting. "
        "2. intro_message: Introduce Amanah Data Solutions (UAE-based regulatory data & governance consultancy), acknowledge their bank's data/compliance priorities, and offer a complimentary Data Assessment. "
        "3. follow_up_message: A polite, brief follow-up checking if they had a chance to consider a 20-minute discussion on data quality and CBUAE/BCBS 239 readiness. "
        "Return ONLY valid JSON with string keys 'connection_request', 'intro_message', and 'follow_up_message'."
    )
    try:
        client = openai_client()
        response = client.chat.completions.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"}
        )
        content = response.choices[0].message.content
        generated = json.loads(content)
        messages = {
            "connection_request": clean_value(generated.get("connection_request")),
            "intro_message": clean_value(generated.get("intro_message")),
            "follow_up_message": clean_value(generated.get("follow_up_message")),
        }
        if not all(messages.values()):
            raise ValueError("Incomplete messages.")
    except Exception:
        messages = build_fallback_linkedin(person_name, designation, bank_name)

    frame.at[row_index, "Generated Connection Request"] = messages["connection_request"]
    frame.at[row_index, "Generated Intro Message"] = messages["intro_message"]
    frame.at[row_index, "Generated Follow-Up Message"] = messages["follow_up_message"]
    save_contacts(frame)
    return jsonify(messages=messages, linkedin=clean_value(row["LinkedIn"]))


@app.post("/api/insights")
def ai_insights():
    records = get_records()
    stats = dashboard_stats(records)
    coverage = coverage_for(records)
    summary = {
        "stats": stats,
        "bank_coverage": [
            {"bank": bank["bank"], "found_roles": bank["found"], "missing_roles": bank["missing"]}
            for bank in coverage
        ],
        "contacts_missing_email": sum(not record["Email"] for record in records),
        "contacts_missing_linkedin": sum(not record["LinkedIn"] for record in records),
        "approved_contacts": stats["approved_contacts"],
    }
    try:
        client = openai_client()
        response = client.responses.create(
            model=os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
            input=(
                "Give 4-6 short, prioritized recommendations for a single-user B2B "
                "contact outreach dashboard. Identify banks missing executives, "
                "contacts missing email, low-coverage banks, who to contact first "
                "(only by bank and role, not private personal details), bank priorities, "
                "and one next action. Use only this aggregate data, do not invent facts. "
                "Use readable bullet points.\n" + json.dumps(summary)
            ),
        )
        return jsonify(insights=response_text(response))
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503
    except OpenAIError as exc:
        return jsonify(error=f"OpenAI request failed: {exc}"), 502
    except ValueError as exc:
        return jsonify(error=str(exc)), 502


@app.get("/export/contacts")
def export_contacts():
    if not WORKBOOK_PATH.exists():
        flash("Upload an Excel file before exporting contacts.", "warning")
        return redirect(url_for("index"))
    return send_file(WORKBOOK_PATH, as_attachment=True, download_name="enriched_contacts.xlsx")


@app.get("/export/report")
def export_report():
    if not WORKBOOK_PATH.exists():
        flash("Upload an Excel file before exporting a report.", "warning")
        return redirect(url_for("index"))
    return send_file(WORKBOOK_PATH, as_attachment=True, download_name="contacts_report.xlsx")


@app.errorhandler(413)
def file_too_large(_error):
    flash("The Excel file is too large. Maximum upload size is 16 MB.", "danger")
    return redirect(url_for("index"))


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
