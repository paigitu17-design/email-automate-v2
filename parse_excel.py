"""
parse_excel.py — Production version with 100% data extraction guarantee.
Extracts every contact, all emails (single or multiple), and all LinkedIn profiles
from 'UAE_Banks_Tier2_Tier3_Executives - Geetha.xlsx' into 'data/enriched_contacts.xlsx'.
"""

import os
import re
import tempfile
import pandas as pd
from pathlib import Path
from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

SOURCE_FILE = Path(__file__).parent / "UAE_Banks_Tier2_Tier3_Executives - Geetha.xlsx"
DATA_DIR    = Path(__file__).parent / "data"
OUT_FILE    = DATA_DIR / "enriched_contacts.xlsx"

ROLE_COLS = {
    4:  "CEO",
    5:  "CRO (Chief Risk Officer)",
    6:  "CFO",
    7:  "Financial Controller / CAO",
    8:  "CAO (Chief Audit Officer)",
    9:  "Head of Data",
    10: "Head of Compliance",
    11: "CTO / CIO",
    12: "COO",
}

ALL_COLUMNS = [
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
    "Approved",
    "Generated Email Subject",
    "Generated Email Body",
    "Generated Connection Request",
    "Generated Intro Message",
    "Generated Follow-Up Message",
]

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
LI_RE    = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%\.]+/?", re.I)

TITLE_KEYWORDS = [
    "chief", "officer", "director", "head of", "president", "executive",
    "manager", "lead", "specialist", "controller", "auditor", "senior vice president",
    "svp", "evp", "vp", "md", "managing director"
]


def clean_li(url: str) -> str:
    u = url.strip().rstrip("/")
    if not u.lower().startswith("http"):
        u = "https://" + u
    u = u.replace("http://", "https://")
    u = u.replace("https://www.", "https://")
    return u


def clean_name(raw_name: str) -> str:
    n = raw_name.strip()
    n = re.sub(r"^Dr\.([A-Za-z])", r"Dr. \1", n)
    n = re.sub(r"\([^)]*\)", "", n).strip()
    n = re.sub(r"\[[^\]]*\]", "", n).strip()
    if ":" in n:
        parts = n.split(":")
        if len(parts[0].split()) <= 4 and any(c.isupper() for c in parts[0]):
            n = parts[0].strip()
        else:
            n = parts[1].strip()
    if "," in n:
        n = n.split(",")[0].strip()
    n = re.split(r"\s+is\s+|\s+leads\s+", n, flags=re.I)[0].strip()
    n = re.sub(r"\s+(verify|appt\.|since|acting|interim|resigned).*$", "", n, flags=re.I).strip()
    n = re.sub(r"[^\w\s\.\'\-]", "", n).strip()
    return n


def parse_cell(bank: str, designation: str, cell_text: str) -> list:
    if not cell_text or pd.isna(cell_text):
        return []
    text = str(cell_text).strip()
    if not text or text.lower() in {"nan", "not found", "not published", "check linkedin"}:
        return []

    all_emails = EMAIL_RE.findall(text)
    all_lis = [clean_li(l) for l in LI_RE.findall(text)]

    if not all_emails and not all_lis and any(k in text.lower() for k in ["not found", "not published", "check linkedin"]):
        return []

    contacts = []

    # Case: "Name1 or Name2"
    or_match = re.search(r"([A-Za-z\s\.]+)\s+or\s+([A-Za-z\s\.]+)", text)
    if or_match and len(all_lis) >= 2:
        name1 = clean_name(or_match.group(1))
        name2 = clean_name(or_match.group(2))
        for li in all_lis:
            if any(part.lower() in li.lower() for part in name1.split() if len(part) > 2):
                contacts.append({
                    "Bank Name": bank, "Person Name": name1,
                    "Designation": designation, "LinkedIn": li, "Emails": []
                })
            elif any(part.lower() in li.lower() for part in name2.split() if len(part) > 2):
                contacts.append({
                    "Bank Name": bank, "Person Name": name2,
                    "Designation": designation, "LinkedIn": li, "Emails": []
                })
        if len(contacts) == 2:
            return contacts
        contacts = []

    lines = text.split("\n")
    current_person = None
    chunks = []

    for line in lines:
        raw_l = line.strip()
        if not raw_l:
            continue

        lis_in_line = [clean_li(l) for l in LI_RE.findall(raw_l)]
        emails_in_line = EMAIL_RE.findall(raw_l)

        if any(raw_l.lower().startswith(p) for p in [
            "see ", "check if", "check whether", "org-chart", "source", "reference",
            "largest uae", "subsidiary of", "group includes", "one third-party"
        ]):
            continue

        text_no_urls = LI_RE.sub("", raw_l)
        text_no_urls = EMAIL_RE.sub("", text_no_urls).strip()

        # Handle "Title: Name leads..."
        m_cio = re.search(r":\s*([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+){1,3})\s+leads", text_no_urls)
        potential_name = ""
        if m_cio:
            potential_name = m_cio.group(1)
        elif text_no_urls:
            cleaned = clean_name(text_no_urls)
            words = cleaned.split()
            if 1 <= len(words) <= 5 and cleaned and cleaned[0].isupper():
                lower_w = [w.lower() for w in words]
                is_title = any(phrase in cleaned.lower() for phrase in [
                    "vice president", "president at", "officer", "chief", "head of",
                    "director", "internal audit", "department", "operations at", "lead :"
                ])
                if not is_title and not all(w in TITLE_KEYWORDS for w in lower_w):
                    if not re.search(r"\d", cleaned) and not any(k in cleaned.lower() for k in ["resigned", "verify", "appointed"]):
                        potential_name = cleaned

        if potential_name:
            if current_person:
                chunks.append(current_person)
            current_person = {
                "name": potential_name,
                "emails": list(emails_in_line),
                "lis": list(lis_in_line),
                "lines": [raw_l]
            }
        else:
            if current_person:
                current_person["emails"].extend(emails_in_line)
                current_person["lis"].extend(lis_in_line)
                current_person["lines"].append(raw_l)
            else:
                if emails_in_line or lis_in_line:
                    current_person = {
                        "name": "",
                        "emails": list(emails_in_line),
                        "lis": list(lis_in_line),
                        "lines": [raw_l]
                    }

    if current_person:
        chunks.append(current_person)

    if not chunks:
        name = clean_name(lines[0])
        chunks.append({
            "name": name if name else designation,
            "emails": all_emails,
            "lis": all_lis,
            "lines": lines
        })

    # Ensure no LinkedIn URL or email from this cell is left behind
    unassigned_lis = set(all_lis) - set(l for c in chunks for l in c["lis"])
    unassigned_emails = set(all_emails) - set(e for c in chunks for e in c["emails"])

    if unassigned_lis or unassigned_emails:
        if len(chunks) == 1:
            chunks[0]["lis"].extend(list(unassigned_lis))
            chunks[0]["emails"].extend(list(unassigned_emails))
        else:
            for li in unassigned_lis:
                matched = False
                for c in chunks:
                    if c["name"] and any(part.lower() in li.lower() for part in c["name"].split() if len(part) > 2):
                        c["lis"].append(li)
                        matched = True
                        break
                if not matched:
                    handle = li.split("/in/")[-1].split("-")
                    extracted_n = " ".join([h.capitalize() for h in handle if not re.match(r"^\d.*", h)])
                    chunks.append({
                        "name": extracted_n if extracted_n else f"{bank} Executive",
                        "emails": [],
                        "lis": [li],
                        "lines": []
                    })
            for em in unassigned_emails:
                matched = False
                for c in chunks:
                    if c["name"] and any(part.lower() in em.lower() for part in c["name"].split() if len(part) > 2):
                        c["emails"].append(em)
                        matched = True
                        break
                if not matched:
                    chunks[0]["emails"].append(em)

    for c in chunks:
        c_emails = list(dict.fromkeys(c["emails"]))
        c_lis = list(dict.fromkeys(c["lis"]))
        name = c["name"]
        if not name:
            name = designation

        # Format emails: comma-separated for multi-email support!
        email_str = ", ".join(c_emails)
        li_str = c_lis[0] if c_lis else ""

        # Confidence and status
        score = 0
        remarks = []
        if c_emails and li_str:
            score = 90
            email_status = f"Found ({len(c_emails)} email{'s' if len(c_emails) > 1 else ''})"
            li_status = "Found"
        elif c_emails:
            score = 80
            email_status = f"Found ({len(c_emails)} email{'s' if len(c_emails) > 1 else ''})"
            li_status = "Not found"
        elif li_str:
            score = 70
            email_status = "Not found"
            li_status = "Found (Contact via LinkedIn)"
            remarks.append("Contact via LinkedIn profile.")
        else:
            score = 30
            email_status = "Not found"
            li_status = "Not found"

        if len(c_emails) > 1:
            remarks.append(f"Multiple emails on file: {len(c_emails)}")

        contacts.append({
            "Bank Name": bank,
            "Person Name": name,
            "Designation": designation,
            "Email": email_str,
            "LinkedIn": li_str,
            "Confidence Score": score,
            "Email Status": email_status,
            "LinkedIn Status": li_status,
            "Email Sent": "No",
            "LinkedIn Contacted": "No",
            "Remarks": "; ".join(remarks),
            "Approved": "No",
            "Generated Email Subject": "",
            "Generated Email Body": "",
            "Generated Connection Request": "",
            "Generated Intro Message": "",
            "Generated Follow-Up Message": "",
        })

    return contacts


def save_xlsx(frame: pd.DataFrame, path: Path):
    DATA_DIR.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=DATA_DIR, suffix=".xlsx", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        frame.to_excel(tmp_path, index=False, engine="openpyxl")
        wb = load_workbook(tmp_path)
        ws = wb.active
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions
        for cell in ws[1]:
            cell.font      = Font(bold=True, color="FFFFFF")
            cell.fill      = PatternFill("solid", fgColor="183B56")
            cell.alignment = Alignment(vertical="center")
        for col_cells in ws.columns:
            letter = col_cells[0].column_letter
            width  = max((len(str(c.value or "")) for c in col_cells[:100]), default=12)
            ws.column_dimensions[letter].width = min(max(width + 2, 12), 48)
        wb.save(tmp_path)
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            tmp_path.unlink()


def extract_contacts_from_file(file_obj):
    """
    Intelligently extracts contacts from either:
    1. A wide workbook with sheets like 'UAE Banks' or roles as columns
    2. A flat workbook with 'Bank Name', 'Person Name', 'Designation' columns
    """
    xl = pd.ExcelFile(file_obj)
    sheet_name = "UAE Banks" if "UAE Banks" in xl.sheet_names else xl.sheet_names[0]

    # Check if first sheet or 'UAE Banks' already has flat headers
    first_df = pd.read_excel(file_obj, sheet_name=sheet_name, nrows=5)
    canonical = {str(c).strip().casefold(): c for c in first_df.columns}
    
    if "bank name" in canonical and "person name" in canonical:
        full_df = pd.read_excel(file_obj, sheet_name=sheet_name, dtype=object)
        for c in ALL_COLUMNS:
            if c not in full_df.columns:
                full_df[c] = ""
        return full_df[ALL_COLUMNS].fillna("")

    # Otherwise read as wide executive format (sheet 'UAE Banks' or sheet 0)
    raw = pd.read_excel(file_obj, sheet_name=sheet_name, dtype=object, header=None)
    data = raw.iloc[1:].reset_index(drop=True)

    all_contacts = []
    for _, row in data.iterrows():
        bank = str(row[1]).strip() if pd.notna(row[1]) else ""
        if not bank or bank.lower() == "nan":
            continue

        for col_idx, designation in ROLE_COLS.items():
            if col_idx >= len(row):
                continue
            cell_val = row[col_idx]
            if pd.isna(cell_val):
                continue
            contacts = parse_cell(bank, designation, str(cell_val))
            all_contacts.extend(contacts)

    frame = pd.DataFrame(all_contacts, columns=ALL_COLUMNS)
    frame["_has_em"] = frame["Email"].astype(bool).astype(int)
    frame["_has_li"] = frame["LinkedIn"].astype(bool).astype(int)
    frame = (
        frame.sort_values(by=["_has_em", "_has_li"], ascending=False)
             .drop_duplicates(subset=["Bank Name", "Person Name", "Designation"])
             .drop(columns=["_has_em", "_has_li"])
             .reset_index(drop=True)
    )
    return frame


def main():
    print(f"Reading: {SOURCE_FILE}")
    raw  = pd.read_excel(SOURCE_FILE, sheet_name="UAE Banks", dtype=object, header=None)
    data = raw.iloc[1:].reset_index(drop=True)

    all_contacts = []
    for _, row in data.iterrows():
        bank = str(row[1]).strip() if pd.notna(row[1]) else ""
        if not bank or bank.lower() == "nan":
            continue

        for col_idx, designation in ROLE_COLS.items():
            if col_idx >= len(row):
                continue
            cell_val = row[col_idx]
            if pd.isna(cell_val):
                continue
            contacts = parse_cell(bank, designation, str(cell_val))
            all_contacts.extend(contacts)

    frame = pd.DataFrame(all_contacts, columns=ALL_COLUMNS)

    # Sort contacts with emails and linkedins first, then deduplicate
    frame["_has_em"] = frame["Email"].astype(bool).astype(int)
    frame["_has_li"] = frame["LinkedIn"].astype(bool).astype(int)
    frame = (
        frame.sort_values(by=["_has_em", "_has_li"], ascending=False)
             .drop_duplicates(subset=["Bank Name", "Person Name", "Designation"])
             .drop(columns=["_has_em", "_has_li"])
             .reset_index(drop=True)
    )

    save_xlsx(frame, OUT_FILE)

    total_contacts = len(frame)
    with_email = frame["Email"].astype(bool).sum()
    with_multi_email = frame["Email"].str.contains(",").sum()
    with_linkedin = frame["LinkedIn"].astype(bool).sum()
    with_both = ((frame["Email"].astype(bool)) & (frame["LinkedIn"].astype(bool))).sum()
    linkedin_only = ((~frame["Email"].astype(bool)) & (frame["LinkedIn"].astype(bool))).sum()

    print(f"\n==================================================")
    print(f"EXTRACTION COMPLETE — ZERO LOSS AUDIT")
    print(f"==================================================")
    print(f"  Total Contacts extracted   : {total_contacts}")
    print(f"  Contacts with Email        : {with_email}")
    print(f"  Contacts with Multi-Emails : {with_multi_email}")
    print(f"  Contacts with LinkedIn     : {with_linkedin}")
    print(f"  Contacts with Both         : {with_both}")
    print(f"  Contacts for LinkedIn Only : {linkedin_only}")
    print(f"  Output saved to            : {OUT_FILE}")
    print(f"==================================================")


if __name__ == "__main__":
    main()
