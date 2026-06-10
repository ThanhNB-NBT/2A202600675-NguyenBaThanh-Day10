from __future__ import annotations

from dataclasses import asdict
from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any

import requests

from core.config import Settings
from core.utils import normalize_whitespace, read_json, write_json


@dataclass(frozen=True)
class PaperRecord:
    # Schema trung gian dùng chung cho cả pipeline. Các bước sau chỉ cần đọc
    # PaperRecord thay vì phụ thuộc trực tiếp vào cấu trúc JSON khá lộn xộn của Crossref.
    paper_id: str
    title: str
    summary: str
    authors: list[str]
    categories: list[str]
    primary_category: str
    published: str
    updated: str
    abs_url: str
    pdf_url: str
    comment: str


def _first(value: Any, default: str = "") -> str:
    # Crossref thường trả title/subtitle dưới dạng list. Hàm nhỏ này lấy phần tử
    # đầu tiên để các bước parse phía dưới luôn làm việc với chuỗi đơn giản.
    if isinstance(value, list) and value:
        return str(value[0] or default)
    if value is None:
        return default
    return str(value)


def _clean_abstract(value: str) -> str:
    # Abstract của Crossref hay chứa tag JATS/XML như <jats:p>. Ta bỏ tag trước
    # khi normalize khoảng trắng để summary sạch hơn cho cả embedding lẫn report.
    text = value.replace("<jats:p>", " ").replace("</jats:p>", " ")
    text = text.replace("<jats:title>", " ").replace("</jats:title>", " ")
    while "<" in text and ">" in text:
        start = text.find("<")
        end = text.find(">", start)
        if end < start:
            break
        text = f"{text[:start]} {text[end + 1:]}"
    return normalize_whitespace(text)


def _date_from_parts(item: dict[str, Any], key: str) -> str:
    # Crossref lưu ngày theo dạng {"date-parts": [[year, month, day]]}. Nếu thiếu
    # month/day thì dùng 01 để vẫn tạo được ngày ISO hợp lệ.
    parts = item.get(key, {}).get("date-parts", [[]])
    if not parts or not parts[0]:
        return ""
    year = int(parts[0][0])
    month = int(parts[0][1]) if len(parts[0]) > 1 else 1
    day = int(parts[0][2]) if len(parts[0]) > 2 else 1
    return f"{year:04d}-{month:02d}-{day:02d}"


def parse_crossref_payload(payload: dict) -> list[PaperRecord]:
    """Parse a Crossref API payload into normalized paper records."""
    records: list[PaperRecord] = []
    items = payload.get("message", {}).get("items", [])
    for item in items:
        # Chỉ giữ record có DOI, title và abstract vì đây là ba trường tối thiểu
        # để định danh tài liệu, hiển thị tên, và tạo nội dung cho RAG.
        doi = normalize_whitespace(str(item.get("DOI", "")))
        title = normalize_whitespace(_first(item.get("title")))
        summary = _clean_abstract(str(item.get("abstract", "")))
        if not doi or not title or not summary:
            continue

        authors = []
        for author in item.get("author", []) or []:
            given = normalize_whitespace(str(author.get("given", "")))
            family = normalize_whitespace(str(author.get("family", "")))
            name = normalize_whitespace(f"{given} {family}")
            if name:
                authors.append(name)

        categories = [normalize_whitespace(str(value)) for value in item.get("subject", []) or []]
        categories = [value for value in categories if value]
        # Ưu tiên ngày publish thật; nếu thiếu thì fallback sang ngày record được tạo
        # để freshness report vẫn có dữ liệu thay vì làm rơi record.
        published = _date_from_parts(item, "published-print") or _date_from_parts(item, "published-online")
        published = published or _date_from_parts(item, "created")
        updated = _date_from_parts(item, "updated") or _date_from_parts(item, "deposited") or published

        # PDF không phải record nào cũng có, nên trường này để rỗng nếu Crossref
        # không cung cấp link content-type là PDF.
        links = item.get("link", []) or []
        pdf_url = ""
        for link in links:
            if "pdf" in str(link.get("content-type", "")).lower():
                pdf_url = str(link.get("URL", ""))
                break

        records.append(
            PaperRecord(
                paper_id=f"doi:{doi.lower()}",
                title=title,
                summary=summary,
                authors=authors or ["Unknown author"],
                categories=categories or ["Uncategorized"],
                primary_category=(categories or ["Uncategorized"])[0],
                published=published,
                updated=updated,
                abs_url=str(item.get("URL", "")),
                pdf_url=pdf_url,
                comment=normalize_whitespace(_first(item.get("subtitle"))),
            )
        )
    return records


def fetch_source_records(settings: Settings) -> list[PaperRecord]:
    """Fetch Crossref records, save raw artifacts, and return parsed records."""
    # Query/filter/rows lấy từ config để khi muốn đổi chủ đề hoặc số lượng paper
    # chỉ cần sửa settings/env, không cần đụng logic ingestion.
    params = {
        "query": settings.source_query,
        "filter": settings.source_filter,
        "rows": settings.max_results,
    }
    headers = {"User-Agent": "day10-data-observability-lab/0.1 (mailto:student@example.com)"}

    last_error: Exception | None = None
    for attempt in range(3):
        try:
            response = requests.get("https://api.crossref.org/works", params=params, headers=headers, timeout=30)
            # 429/503 thường là rate limit hoặc service tạm bận. Backoff ngắn giúp
            # lab bền hơn mà không làm flow phức tạp.
            if response.status_code in {429, 503}:
                time.sleep(2**attempt)
                continue
            response.raise_for_status()
            payload = response.json()
            write_json(settings.paths.raw_api_response, payload)
            records = parse_crossref_payload(payload)
            if not records:
                raise RuntimeError("Crossref returned no parseable records.")
            write_json(settings.paths.raw_records_json, [asdict(record) for record in records])
            return records
        except Exception as exc:  # pragma: no cover - depends on external API
            last_error = exc
            time.sleep(2**attempt)

    # Nếu network lỗi nhưng đã có snapshot từ lần chạy trước, dùng lại snapshot để
    # người chấm vẫn reproduce được pipeline offline.
    if settings.paths.raw_records_json.exists():
        return load_raw_records(settings.paths.raw_records_json)
    raise RuntimeError(f"Could not fetch Crossref records and no local raw snapshot exists: {last_error}")


def load_raw_records(path: Path) -> list[PaperRecord]:
    """Load a saved raw records JSON snapshot."""
    payload = read_json(path)
    return [PaperRecord(**item) for item in payload]
