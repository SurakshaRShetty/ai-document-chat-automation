AI Document Chat System — Automation Guide
Coverage
- Playwright + pytest browser automation using Chromium.
- Loads credentials and PDF path from .env; loads question/reference-answer pairs from questions.json.
- Attempts signup, logs in, uploads the PDF, asks configured questions sequentially, and checks API/UI responses.
- Compares expected and actual answers using keyword overlap: PASS >= 60%, REVIEW 30–59%, FAIL < 30%. This is a heuristic, not proof of semantic or factual correctness.
- Saves question_results_small_test.csv after each question.
- Asks one unrelated question and saves its response to unanswerable_question_result.csv; its refusal-phrase check is heuristic and requires manual review.
- Checks logout by confirming navigation to / and removal of access_token and document_id from localStorage. Probes /chat after logout and prints a review note if it remains accessible.
- Pytest creates small_test_report.html.
Start the application
Backend terminal:
cd "C:\SURAKSHA - PROJECTS\AI-Document-Chat-System-main\backend"
python -m uvicorn app.main:app --reload
Use the backend's existing virtual environment if required.

Frontend terminal:
cd "C:\SURAKSHA - PROJECTS\AI-Document-Chat-System-main\frontend"
npm run dev
Automation terminal:
cd "C:\SURAKSHA - PROJECTS\AI-Document-Chat-System-main\ai-chatbot-automation"
.\venv\Scripts\Activate.ps1
python -m pytest -v -s test_all_questions.py --html=small_test_report.html --self-contained-html
Required files/settings
- .env must contain APP_EMAIL, APP_PASSWORD, and PDF_PATH.
- questions.json must contain question and expected_answer fields for each question.
- Do not share or commit .env credentials.
Known limitations / final manual checks
1. Questions are read from questions.json; the script does not extract test questions from the PDF automatically.
2. Keyword overlap can produce false positives/negatives. Manually review every important answer.
3. Refusal phrase detection can miss valid refusals or misclassify responses. Manually inspect the unanswerable response.
4. Client-side logout does not itself prove backend security. Confirm protected React routes redirect and protected API endpoints reject requests without a valid token.
5. If the AI provider quota is exhausted, the test stops and saves partial results.
6. Signup may not navigate when the account already exists; the script then attempts login.