# DoNotStressGrokkies

Local Flask check-in for **students** (not advisors). You answer a short form, Gemini analyses it, Logic finalizes the AI-enriched record, and you can contact SIT Counselling. Nothing is written to disk unless you opt in on the result page.

Gemini is **required**. There is no Logic-only / fake-tips path when the API key is missing or Gemini fails.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Gemini API key (required)

Every check-in calls `ai_manager.analyse_student(...)`. Set a Google Gemini key in the environment:

```bash
export GEMINI_API_KEY="your-key-here"
```

Windows (PowerShell):

```powershell
$env:GEMINI_API_KEY="your-key-here"
```

Create a key in [Google AI Studio](https://aistudio.google.com/apikey). If the key is missing or Gemini fails, the app shows an AI-required error page (with official counselling contacts). It does **not** invent `soft_label` / tips from the form numbers alone.

## Run locally

From the project root:

```bash
python app.py
```

Or:

```bash
export FLASK_APP=app
flask run
```

Then open [http://127.0.0.1:5000](http://127.0.0.1:5000).

Optional:

- `FLASK_SECRET_KEY` — cookie signing key (a default is used for local dev)
- `DONOTSTRESS_DATA_PATH` — JSON file used only after opt-in save
- `PORT` — defaults to 5000

## What happens after submit

1. `io_manager.validate_student_form(...)` checks the form.
2. Gemini **must** succeed via `ai_manager.analyse_student(...)`.
3. On AI failure, `io_manager.format_ai_error(...)` / `format_ai_unavailable_error` builds the error page. Logic is not used as a product substitute.
4. On AI success only, `logic_manager.apply_logic(...)` (alias `finalize_outcome`) finalizes the record (`source` becomes `ai_logic`).
5. The result page uses `format_soft_label`, `format_tips`, and `format_speak_to_advisor_panel`.
6. Save runs only if you tick the box and click **Save my check-in**, which calls `data_manager.save_record(record, opt_in=True)` for successful AI-processed records.

## Support contacts

The Speak to advisor panel always uses these official contacts only:

- Email: [SITCounselling@SingaporeTech.edu.sg](mailto:SITCounselling@SingaporeTech.edu.sg)
- Helpline: 6592 2030

## Tests

```bash
pytest
```
