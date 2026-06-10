from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd

from core.utils import compact_join, normalize_whitespace
from ingestion.crossref import PaperRecord


def _parse_date(value: str) -> datetime | None:
    # Dùng pandas để parse linh hoạt nhiều kiểu ngày khác nhau, rồi ép về UTC
    # để phép tính age_days nhất quán giữa các máy.
    if not value:
        return None
    parsed = pd.to_datetime(value, errors="coerce", utc=True)
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def build_clean_dataframe(records: list[PaperRecord], run_date: datetime) -> pd.DataFrame:
    """Clean raw paper records into a dataframe ready for embedding."""
    rows = []
    run_at = run_date.astimezone(UTC) if run_date.tzinfo else run_date.replace(tzinfo=UTC)
    for record in records:
        # Normalize ngay từ đầu để các check sau không bị lệch vì newline,
        # nhiều khoảng trắng, hoặc chuỗi rỗng giả.
        title = normalize_whitespace(record.title)
        summary = normalize_whitespace(record.summary)
        authors = [normalize_whitespace(author) for author in record.authors if normalize_whitespace(author)]
        categories = [normalize_whitespace(category) for category in record.categories if normalize_whitespace(category)]
        published_dt = _parse_date(record.published)
        updated_dt = _parse_date(record.updated) or published_dt
        # Record thiếu id/title/summary/date sẽ làm retrieval và freshness sai,
        # nên loại bỏ ở tầng cleaning thay vì để lỗi lan xuống pipeline.
        if not record.paper_id or not title or not summary or published_dt is None:
            continue

        authors_joined = compact_join(authors or ["Unknown author"])
        categories_joined = compact_join(categories or ["Uncategorized"])
        age_days = max(0, (run_at.date() - published_dt.date()).days)
        # Đây là đoạn text chính đưa vào embedding. Ghép title, summary, authors,
        # categories và ngày publish để truy vấn theo nội dung lẫn metadata đều có tín hiệu.
        text_for_embedding = normalize_whitespace(
            " ".join(
                [
                    f"Title: {title}.",
                    f"Summary: {summary}",
                    f"Authors: {authors_joined}.",
                    f"Categories: {categories_joined}.",
                    f"Published: {published_dt.date().isoformat()}.",
                ]
            )
        )
        rows.append(
            {
                # paper_id được lower-case để lookup exact ổn định, không phụ thuộc
                # cách Crossref viết hoa/thường DOI.
                "paper_id": normalize_whitespace(record.paper_id).lower(),
                "title": title,
                "summary": summary,
                "authors": authors or ["Unknown author"],
                "categories": categories or ["Uncategorized"],
                "primary_category": normalize_whitespace(record.primary_category) or (categories or ["Uncategorized"])[0],
                "published": published_dt.date().isoformat(),
                "updated": (updated_dt or published_dt).date().isoformat(),
                "age_days": age_days,
                "abs_url": normalize_whitespace(record.abs_url),
                "pdf_url": normalize_whitespace(record.pdf_url),
                "comment": normalize_whitespace(record.comment),
                "authors_joined": authors_joined,
                "categories_joined": categories_joined,
                "summary_chars": len(summary),
                "text_for_embedding": text_for_embedding,
            }
        )

    df = pd.DataFrame(rows)
    if df.empty:
        raise ValueError("No valid records remained after cleaning.")
    # DOI là khóa tự nhiên của paper, nên duplicate DOI chỉ giữ một dòng.
    df = df.drop_duplicates(subset=["paper_id"]).copy()
    # Summary quá ngắn thường không đủ thông tin cho RAG và cũng dễ làm metrics nhiễu.
    df = df[df["summary_chars"] >= 40].copy()
    # Sort mới nhất trước để test set/freshness/corruption có thứ tự dễ giải thích.
    df = df.sort_values(["published", "paper_id"], ascending=[False, True]).reset_index(drop=True)
    return df
