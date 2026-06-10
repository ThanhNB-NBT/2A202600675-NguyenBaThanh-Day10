from __future__ import annotations

from typing import Any

import pandas as pd

from core.utils import first_sentence, write_json


def build_test_set(df: pd.DataFrame, output_path) -> list[dict[str, Any]]:
    """Build a small deterministic evaluation set from cleaned papers."""
    # Tối thiểu 3 paper để bộ test không quá mỏng; nếu ít hơn thì metrics rất dễ
    # bị đẹp giả tạo hoặc không đại diện cho retrieval.
    if len(df) < 3:
        raise ValueError("Need at least 3 cleaned papers to build a useful test set.")

    samples: list[dict[str, Any]] = []
    # Chọn các paper mới nhất vì dataframe đã được sort ở bước cleaning. Cách chọn
    # deterministic giúp chạy lại nhiều lần vẫn ra cùng test set.
    selected = df.head(min(8, len(df))).to_dict(orient="records")
    # Mỗi template kiểm tra một năng lực khác nhau của agent: tóm tắt nội dung,
    # đọc tác giả, đọc ngày publish, và đọc category/metadata.
    question_templates = [
        ("summary", "What is the main summary of '{title}'?", lambda row: first_sentence(row["summary"])),
        ("authors", "Who authored '{title}'?", lambda row: row["authors_joined"]),
        ("date", "When was '{title}' published?", lambda row: row["published"]),
        ("categories", "What categories are listed for '{title}'?", lambda row: row["categories_joined"]),
    ]

    for row_index, row in enumerate(selected):
        # Xoay vòng template theo index để test set nhỏ nhưng vẫn có nhiều loại câu hỏi.
        question_type, template, answer_builder = question_templates[row_index % len(question_templates)]
        samples.append(
            {
                "id": f"q{len(samples) + 1:03d}",
                "question_type": question_type,
                # Đặt title trong dấu nháy để retrieval.qa có thể lookup exact title
                # trước khi fallback sang semantic search.
                "question": template.format(title=row["title"]),
                "ground_truth": str(answer_builder(row)),
                # Metrics dùng danh sách này để biết retrieval có lấy đúng document gốc không.
                "ground_truth_doc_ids": [row["paper_id"]],
            }
        )

    write_json(output_path, samples)
    return samples
