"""Audit: verify every single email and linkedin in source is in enriched_contacts.xlsx"""
import pandas as pd
import re

SOURCE = "UAE_Banks_Tier2_Tier3_Executives - Geetha.xlsx"
OUT    = "data/enriched_contacts.xlsx"

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")
LI_RE    = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9\-_%\.]+/?", re.I)

def clean_li(url):
    u = url.strip().rstrip("/")
    if not u.lower().startswith("http"):
        u = "https://" + u
    u = u.replace("http://", "https://")
    u = u.replace("https://www.", "https://")
    return u

raw  = pd.read_excel(SOURCE, sheet_name="UAE Banks", dtype=object, header=None)
data = raw.iloc[1:].reset_index(drop=True)

all_src_emails = set()
all_src_lis    = set()

for _, row in data.iterrows():
    bank = str(row[1]).strip() if pd.notna(row[1]) else ""
    if not bank or bank.lower() == "nan": continue
    for col_idx in range(4, 13):
        if col_idx >= len(row): continue
        val = row[col_idx]
        if pd.isna(val): continue
        txt = str(val).strip()
        all_src_emails.update([e.lower() for e in EMAIL_RE.findall(txt)])
        all_src_lis.update([clean_li(l).lower() for l in LI_RE.findall(txt)])

out_df = pd.read_excel(OUT)
out_emails = set()
for em_str in out_df["Email"].dropna():
    for em in str(em_str).split(","):
        if em.strip():
            out_emails.add(em.strip().lower())

out_lis = set(clean_li(str(l)).lower() for l in out_df["LinkedIn"].dropna() if str(l).strip())

missing_e = all_src_emails - out_emails
missing_l = all_src_lis - out_lis

print("=" * 60)
print("AUDIT RESULTS")
print("=" * 60)
print(f"Total Unique Source Emails   : {len(all_src_emails)}")
print(f"Total Captured Emails        : {len(out_emails)}")
print(f"Missing Emails               : {len(missing_e)} -> {missing_e}")
print()
print(f"Total Unique Source LinkedIn : {len(all_src_lis)}")
print(f"Total Captured LinkedIn      : {len(out_lis)}")
print(f"Missing LinkedIn             : {len(missing_l)} -> {missing_l}")
print("=" * 60)
