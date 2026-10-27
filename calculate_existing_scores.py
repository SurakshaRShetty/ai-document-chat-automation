
import csv
from pathlib import Path
from sentence_transformers import util
from test_all_questions import embedding_model, get_keywords

base = Path(__file__).resolve().parent
source = base / "question_results_small_test.csv"
output = base / "question_results_with_scores.csv"

score_columns = [
    "keyword_precision",
    "keyword_recall",
    "keyword_f1",
    "semantic_similarity",
]

with source.open(encoding="utf-8-sig", newline="") as f:
    rows = list(csv.DictReader(f))

if not rows:
    raise SystemExit("No question rows found in the source CSV.")

fields = list(rows[0].keys())
for column in score_columns:
    if column not in fields:
        fields.append(column)

for i, row in enumerate(rows, start=1):
    expected = row.get("expected_answer", "").strip()
    actual = row.get("chatbot_answer", "").strip()

    if not expected or not actual:
        print(f"Question {i}: skipped because an answer is empty.")
        continue

    expected_words = get_keywords(expected)
    actual_words = get_keywords(actual)

    precision = recall = f1 = 0.0

    if expected_words and actual_words:
        matched = expected_words & actual_words
        precision = len(matched) / len(actual_words)
        recall = len(matched) / len(expected_words)
        if precision + recall:
            f1 = 2 * precision * recall / (precision + recall)

    embeddings = embedding_model.encode(
        [expected, actual],
        convert_to_tensor=True,
    )
    similarity = float(util.cos_sim(embeddings[0], embeddings[1]).item())

    row.update({
        "keyword_precision": round(precision, 4),
        "keyword_recall": round(recall, 4),
        "keyword_f1": round(f1, 4),
        "semantic_similarity": round(similarity, 4),
    })

    print(f"Scored question {i}/{len(rows)}")

with output.open("w", encoding="utf-8-sig", newline="") as f:
    writer = csv.DictWriter(f, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)

print(f"\nDone! Scored {len(rows)} existing question rows.")
print(f"New CSV: {output}")
print("The original CSV was not modified.")
