# Amanah Data Solutions — UAE Banking Executive Outreach & Intelligence

An executive B2B outreach platform designed for Amanah Data Solutions (Masdar City, Abu Dhabi). It parses UAE bank executive workbooks across Tier 1, 2, and 3 financial institutions, generates personalized 4-paragraph consultative proposals, connects directly to Gmail Web Compose, generates LinkedIn outreach sequences, and tracks multi-channel delivery in real time.

---

## Key Features

1. **Zero-Loss UAE Banking Intelligence**:
   - Parses multi-sheet and wide-format bank workbooks across 22 UAE banks (Tier 1, 2, and 3).
   - 100% email and LinkedIn profile extraction.
   - Preserves multi-inbox contacts (simultaneous delivery to all corporate email addresses).

2. **Amanah Consultative Outreach Framework**:
   - **Paragraph 1**: Who Amanah Data Solutions are (UAE regulatory data & governance consultancy).
   - **Paragraph 2**: Specific bank research, role context, and CBUAE / BCBS 239 regulatory burdens.
   - **Paragraph 3**: Tailored Amanah data solutions (automated reporting pipelines & data governance).
   - **Paragraph 4**: Call to Action for a complimentary, zero-obligation Data & Regulatory Assessment.

3. **Multi-Channel Delivery & Live Tracker**:
   - **Direct Gmail Web Compose**: Pre-fills recipients, subject, and 4-paragraph proposal directly in your active Gmail session.
   - **LinkedIn Outreach Sequences**: Tailored connection requests (<300 chars), direct intro messages, and follow-up templates.
   - **Live Pipeline Status**: Interactive tracking (`✓ Emailed` vs `⏳ Not Emailed`, `✓ LI Contacted` vs `⏳ LI Pending`) with live dashboard stats.
   - **Excel Persistence**: Tracking data is automatically saved to `data/enriched_contacts.xlsx`.

---

## Quick Start (Local Run)

1. **Clone the repository**:
   ```bash
   git clone https://github.com/paigitu17-design/email-automate-v2.git
   cd email-automate-v2
   ```

2. **Create a virtual environment & install dependencies**:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure OpenAI API Key (Secure Separate File)**:
   Place your API key in `config/openai_key.txt` or set an environment variable:
   ```bash
   mkdir config
   echo "your_openai_api_key_here" > config/openai_key.txt
   ```
   *(Note: The `config/` directory and `.env` files are in `.gitignore` and are never committed).*

4. **Launch the platform**:
   ```bash
   python app.py
   ```
   Open `http://127.0.0.1:5000` in your web browser.

---

## Deploying on Render (Team Access)

The platform is fully pre-configured for Render:
- `requirements.txt` and `Procfile` are included (`web: gunicorn app:app`).
- In Render:
  1. Click **New +** ➔ **Web Service**.
  2. Connect your GitHub repository (`paigitu17-design/email-automate-v2`).
  3. Under Environment Variables, add:
     - `OPENAI_API_KEY`: *(Your key)*
     - `FLASK_DEBUG`: `0`
  4. Deploy! Your team can access the same shared URL, and each user will draft emails/LinkedIn messages through their own local browser logins.
