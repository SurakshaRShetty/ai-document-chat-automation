import csv
import json
import os
import re
from pathlib import Path
from sentence_transformers import SentenceTransformer, util
import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()
embedding_model = SentenceTransformer(
    "sentence-transformers/all-MiniLM-L6-v2"
)   
APP_URL = "http://localhost:5173/"
EMAIL = os.getenv("APP_EMAIL")
PASSWORD = os.getenv("APP_PASSWORD")
PDF_PATH = os.getenv("PDF_PATH")
BASE_DIR = Path(__file__).resolve().parent
QUESTIONS_FILE = BASE_DIR / "questions.json"
CSV_REPORT = BASE_DIR / "question_results_small_test.csv"
UNANSWERABLE_REPORT = BASE_DIR / "unanswerable_question_result.csv"
UNANSWERABLE_QUESTION = "According to the uploaded Python basics document, what is the capital city of Japan?"
REFUSAL_PHRASES = (
    "the provided document does not contain",
    "the document does not contain information",
    "not mentioned in the provided document",
    "not available in the uploaded document",
    "does not contain information",
    "doesn't contain information",
    "does not provide information",
    "doesn't provide information",
    "does not mention",
    "doesn't mention",
    "not mentioned",
    "not provided",
    "not available",
    "cannot find",
    "can't find",
    "unable to find",
    "not in the document",
    "not covered",
    "outside the document",
    "i don't know",
    "i do not know",
    "insufficient information",
    "no information",
)


def normalize(text):
    return " ".join(str(text).lower().split())

def is_possible_refusal(answer):
    normalized_answer = normalize(answer)
    return any(
        phrase in normalized_answer
        for phrase in REFUSAL_PHRASES
    )


def get_keywords(text):
    stop_words = {"the", "a", "an", "is", "are", "was", "were", "and", "or", "to", "of", "in", "on", "for", "with", "by", "it", "this", "that", "what", "how", "you", "can", "do", "does", "be", "from", "as", "at", "all", "only", "not", "when", "which", "their", "they", "both", "its", "into", "after", "before", "python", "answer", "document"}
    words = re.findall(r"\b[a-zA-Z0-9_]+\b", str(text).lower())
    return {word for word in words if len(word) > 2 and word not in stop_words}



def compare_answer_detailed(expected, actual):
    """Compare answers using keyword and semantic similarity."""

    scores = {
        "keyword_precision": "",
        "keyword_recall": "",
        "keyword_f1": "",
        "semantic_similarity": "",
    }

    if not actual or len(actual.strip()) <= 10:
        return "FAIL", "Chatbot returned an empty or very short answer.", scores

    # Basic safeguard for possible contradictions.
    expected_lower = expected.lower()
    actual_lower = actual.lower()

    expected_words = set(re.findall(r"\b[a-zA-Z]+\b", expected_lower))
    ignored_words = {"not", "never", "no", "be", "is", "are", "was", "were", "am", "been", "being"}
    negations = r"(?:not|never|no|isn't|aren't|wasn't|weren't|cannot|can't)"

    for word in expected_words:
        if word in ignored_words:
            continue

        if (
            re.search(
                rf"\b{negations}\s+(?:\w+\s+){{0,2}}{re.escape(word)}\b",
                actual_lower,
            )
            and re.search(rf"\b{re.escape(word)}\b", expected_lower)
        ):
            return (
                "REVIEW",
                f"Possible contradiction: '{word}' appears negated "
                "in the chatbot answer. Manual verification required.",
                scores,
            )

    expected_keywords = get_keywords(expected)
    actual_keywords = get_keywords(actual)

    if not expected_keywords:
        return "REVIEW", "Expected answer has no usable keywords.", scores

    if not actual_keywords:
        return "FAIL", "Chatbot answer has no usable keywords.", scores

    matched = expected_keywords & actual_keywords

    recall = len(matched) / len(expected_keywords)
    precision = len(matched) / len(actual_keywords)

    if precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)

    expected_embedding = embedding_model.encode(
        expected, convert_to_tensor=True
    )
    actual_embedding = embedding_model.encode(
        actual, convert_to_tensor=True
    )

    semantic_score = float(
        util.cos_sim(expected_embedding, actual_embedding).item()
    )

    scores = {
        "keyword_precision": round(precision, 4),
        "keyword_recall": round(recall, 4),
        "keyword_f1": round(f1, 4),
        "semantic_similarity": round(semantic_score, 4),
    }

    details = (
        f"Keyword precision: {precision:.0%}; "
        f"keyword recall: {recall:.0%}; "
        f"F1 score: {f1:.0%}; "
        f"semantic similarity: {semantic_score:.0%}. "
        "Similarity scores do not guarantee factual correctness."
    )

    if semantic_score >= 0.85 and recall >= 0.60:
        return "PASS", details, scores

    if (f1 >= 0.30 and recall >= 0.25) or semantic_score >= 0.45:
        return "REVIEW", details, scores

    return "FAIL", details, scores


def compare_answer(expected, actual):
    """Keep the existing two-value interface for local tests."""
    result, details, _ = compare_answer_detailed(expected, actual)
    return result, details

def save_csv(path, rows, fieldnames):
    with open(path, "w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def signup_if_needed_then_login(page):
    page.goto(APP_URL + "signup")
    page.get_by_role("textbox", name="Name").fill("Automation Test")
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Password").fill(PASSWORD)
    page.get_by_role("button", name="Signup").click()
    try:
        page.wait_for_url(lambda url: not url.endswith("/signup"), timeout=4000)
    except PlaywrightTimeoutError:
        pass  # Account may already exist.
    page.goto(APP_URL)
    page.get_by_role("textbox", name="Email").fill(EMAIL)
    page.get_by_role("textbox", name="Password").fill(PASSWORD)
    page.get_by_role("button", name="Login").click()
    page.wait_for_url("**/upload", timeout=15000)


def ask_question(page, question):
    page.get_by_role("textbox", name="Ask a question...").fill(question)
    with page.expect_response(lambda r: r.request.method == "POST" and "/chat/ask" in r.url, timeout=60000) as info:
        page.get_by_role("button", name="Ask").click()
    response = info.value
    try:
        data = response.json()
    except Exception:
        data = {}
    detail = str(data.get("detail", "")) if isinstance(data, dict) else ""
    return response.status, data, detail


def test_all_pdf_questions_and_authentication():
    assert EMAIL, "APP_EMAIL is missing from .env"
    assert PASSWORD, "APP_PASSWORD is missing from .env"
    assert PDF_PATH, "PDF_PATH is missing from .env"
    assert Path(PDF_PATH).is_file(), f"PDF not found: {PDF_PATH}"
    assert QUESTIONS_FILE.is_file(), f"questions.json not found: {QUESTIONS_FILE}"
    questions = json.loads(QUESTIONS_FILE.read_text(encoding="utf-8"))
    assert questions, "No questions found in questions.json"
    results, out_results = [], []
    quota_exhausted = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        try:
            signup_if_needed_then_login(page)
            with page.expect_response(lambda r: r.request.method == "POST" and "/documents" in r.url, timeout=60000) as upload_info:
                page.locator('input[type="file"]').set_input_files(str(Path(PDF_PATH).resolve()))
            if upload_info.value.status not in (200, 201):
                raise AssertionError(f"PDF upload failed: HTTP {upload_info.value.status}")
            page.wait_for_url("**/chat", timeout=15000)

            for index, item in enumerate(questions, start=1):
                question_id = item.get("id", index)
                question = str(item["question"]).strip()
                expected = str(item["expected_answer"]).strip()
                answer, result, error = "", "ERROR", ""
                scores = {
                    "keyword_precision": "",
                    "keyword_recall": "",
                    "keyword_f1": "",
                    "semantic_similarity": "",
                }
                print(f"\nTesting question {index}/{len(questions)}: {question}")
                try:
                    status, data, detail = ask_question(page, question)
                    if status == 429:
                        quota_exhausted = True
                        error = "AI provider quota/rate limit reached; remaining questions were not sent."
                    elif status != 200:
                        error = f"Chat API returned HTTP {status}" + (f": {detail}" if detail else "")
                    elif not isinstance(data, dict) or "answer" not in data:
                        error = detail or "API response did not contain an answer."
                    else:
                        returned_question = str(data.get("question", "")).strip()
                        answer = str(data.get("answer", "")).strip()
                        if normalize(returned_question) != normalize(question):
                            error = f"Returned question did not match submitted question: {returned_question!r}"
                        else:
                            result, error, scores = compare_answer_detailed(expected, answer)
                            try:
                                page.get_by_text(answer, exact=False).first.wait_for(state="visible", timeout=5000)
                            except PlaywrightTimeoutError:
                                if result == "PASS":
                                    result = "REVIEW"
                                error = (error + " " if error else "") + "API answer not confirmed visible in UI."
                except Exception as exc:
                    error = f"{type(exc).__name__}: {exc}"
                if error and result == "ERROR":
                    result = "ERROR"
                results.append({
                    "id": question_id,
                    "question": question,
                    "expected_answer": expected,
                    "chatbot_answer": answer,
                    "keyword_precision": scores["keyword_precision"],
                    "keyword_recall": scores["keyword_recall"],
                    "keyword_f1": scores["keyword_f1"],
                    "semantic_similarity": scores["semantic_similarity"],
                    "result": result,
                    "validation_details": error,
                })
                print(f"Result: {result}")
                if error:
                    print(f"Details: {error}")
                save_csv(
                    CSV_REPORT,
                    results,
                    [
                        "id",
                        "question",
                        "expected_answer",
                        "chatbot_answer",
                        "keyword_precision",
                        "keyword_recall",
                        "keyword_f1",
                        "semantic_similarity",
                        "result",
                        "validation_details",
                    ],
                )
                if quota_exhausted:
                    print("Stopping because the AI provider quota is exhausted.")
                    break

            if not quota_exhausted:
                print(f"\nTesting unanswerable question: {UNANSWERABLE_QUESTION}")
                try:
                    status, data, detail = ask_question(page, UNANSWERABLE_QUESTION)
                    answer = str(data.get("answer", "")).strip() if isinstance(data, dict) else ""
                    if status == 429:
                        quota_exhausted = True
                        result, detail = "ERROR", "AI provider quota/rate limit reached."
                    elif status != 200 or not answer:
                        result, detail = "ERROR", detail or f"Chat API returned HTTP {status} or no answer."
                    elif is_possible_refusal(answer):
                        result, detail = "PASS", "Possible refusal detected; manually verify the answer."
                    else:
                        result, detail = "REVIEW", "No recognized refusal phrase; manually check for hallucination."
                    out_results.append({"question": UNANSWERABLE_QUESTION, "chatbot_answer": answer, "result": result, "details": detail})
                except Exception as exc:
                    out_results.append({"question": UNANSWERABLE_QUESTION, "chatbot_answer": "", "result": "ERROR", "details": f"{type(exc).__name__}: {exc}"})
                save_csv(UNANSWERABLE_REPORT, out_results, ["question", "chatbot_answer", "result", "details"])
                print(f"Unanswerable result: {out_results[-1]['result']} — {out_results[-1]['details']}")

            # Header.jsx removes these localStorage values and navigates to '/'.
            if not quota_exhausted:
                print("\nTesting logout...")
                try:
                    page.get_by_role("button", name="Logout").click()
                    page.wait_for_url(APP_URL, timeout=10000)
                    assert page.evaluate("localStorage.getItem('access_token')") is None, "access_token remains after logout"
                    assert page.evaluate("localStorage.getItem('document_id')") is None, "document_id remains after logout"
                    print("Logout PASS: navigated to login route and cleared client-side values.")
                    page.goto(APP_URL + "chat")
                    page.wait_for_timeout(1000)
                    if page.url.rstrip("/") == (APP_URL + "chat").rstrip("/"):
                        print("Authentication REVIEW: /chat did not redirect after logout. Check React route guards and backend authorization.")
                    else:
                        print("Protected-route probe: /chat redirected after logout.")
                except Exception as exc:
                    print(f"Logout check ERROR: {type(exc).__name__}: {exc}")

            passed = sum(r["result"] == "PASS" for r in results)
            failed = sum(r["result"] == "FAIL" for r in results)
            review = sum(r["result"] == "REVIEW" for r in results)
            errors = sum(r["result"] == "ERROR" for r in results)
            print("\n========== TEST SUMMARY ==========")
            print(f"Questions in source: {len(questions)}")
            print(f"Questions processed: {len(results)} | Passed: {passed} | Failed: {failed} | Review: {review} | Errors: {errors}")
            print(f"Question CSV: {CSV_REPORT}")
            print(f"Unanswerable CSV: {UNANSWERABLE_REPORT}")
            print("==================================")
            if quota_exhausted:
                pytest.skip("AI provider quota was exhausted. Partial results were saved.")
            assert len(results) == len(questions), f"Expected {len(questions)} results, recorded {len(results)}."
            assert not any(r["result"] == "ERROR" for r in results), "One or more questions had errors; inspect CSV."
        finally:
            browser.close()


def test_refusal_detection():
    assert is_possible_refusal(
        "The provided document does not contain information "
        "about the capital city of Japan."
    )

    assert is_possible_refusal(
        "The document does not mention that topic."
    )

    assert not is_possible_refusal(
        "The capital city of Japan is Tokyo."
    )

    print("All refusal detection checks passed.")



def test_compare_answer():
    expected = (
        "Python is a high-level interpreted programming "
        "language."
    )

    # 1. A relevant answer should pass.
    result, details = compare_answer(
        expected,
        "Python is a high-level, interpreted programming "
        "language used for automation."
    )
    print("Relevant answer:", result, details)
    assert result == "PASS", details

    # 2. A paraphrased answer should pass.
    result, details = compare_answer(
        expected,
        "Python is a programming language that uses an "
        "interpreter and provides a high level of abstraction."
    )
    print("Paraphrased answer:", result, details)
    assert result == "PASS", details

    # 3. An unrelated answer should fail.
    result, details = compare_answer(
        expected,
        "Elephants live in forests and eat plants."
    )
    print("Unrelated answer:", result, details)
    assert result == "FAIL", details

    # 4. An empty answer should fail.
    result, details = compare_answer(expected, "")
    print("Empty answer:", result, details)
    assert result == "FAIL", details

    # 5. A contradictory answer must not be accepted as PASS.
    result, details = compare_answer(
        expected,
        "Python is a high-level programming language, "
        "but it is not interpreted."
    )
    print("Contradictory answer:", result, details)
    assert result != "PASS", (
        "A contradictory answer was incorrectly marked PASS: "
        + details
    )

    print("All answer comparison checks passed.")
