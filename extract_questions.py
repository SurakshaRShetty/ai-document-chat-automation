
import json
import re
from pathlib import Path

from pypdf import PdfReader

BASE_DIR = Path(__file__).resolve().parent

PDF_PATH = BASE_DIR / "rag_chatbot_small_test_qa.pdf"
OUTPUT_PATH = BASE_DIR / "questions.json"


def extract_questions():
    if not PDF_PATH.is_file():
        raise FileNotFoundError(f"PDF not found: {PDF_PATH}")

    reader = PdfReader(str(PDF_PATH))
    pdf_text = "\n".join(
        page.extract_text() or "" for page in reader.pages
    )

    pattern = re.compile(
        r"Question\s+(\d+):\s*(.*?)"
        r"\s*Reference answer:\s*(.*?)"
        r"(?=\s*Question\s+\d+:|\s*Testing note:|\Z)",
        re.DOTALL | re.IGNORECASE,
    )

    questions = []

    for match in pattern.finditer(pdf_text):
        number = int(match.group(1))
        question = re.sub(r"\s+", " ", match.group(2)).strip()
        answer = re.sub(r"\s+", " ", match.group(3)).strip()

        if question and answer:
            questions.append({
                "id": number,
                "question": question,
                "expected_answer": answer,
            })

    questions.sort(key=lambda item: item["id"])

    if len(questions) != 10:
        raise ValueError(
            f"Expected 10 questions, extracted {len(questions)}. "
            "Check the PDF text and question format."
        )

    OUTPUT_PATH.write_text(
        json.dumps(questions, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"Questions extracted: {len(questions)}")
    print(f"Saved to: {OUTPUT_PATH}")

    for item in questions:
        print(f"\nQ{item['id']}: {item['question']}")
        print(f"Reference answer: {item['expected_answer']}")


if __name__ == "__main__":
    extract_questions()
