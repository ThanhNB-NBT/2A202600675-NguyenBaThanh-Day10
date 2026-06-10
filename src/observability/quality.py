from __future__ import annotations

from typing import Any

import pandas as pd

from core.config import Settings
from core.utils import write_json


def run_data_quality_checks(df: pd.DataFrame, settings: Settings, report_name: str) -> dict[str, Any]:
    """Run data quality checks and persist the report."""
    total_rows = int(len(df))
    # Mỗi check trả về passed + observed để report vừa đọc được bởi người, vừa dễ
    # dùng lại trong script chấm tự động.
    checks = [
        {
            # Dataset quá ít dòng thì retrieval/evaluation không còn ý nghĩa.
            "name": "row_count_at_least_3",
            "passed": total_rows >= 3,
            "observed": total_rows,
        },
        {
            # paper_id là khóa nối giữa test set, retrieved docs và metrics.
            "name": "paper_id_not_null",
            "passed": bool(df["paper_id"].notna().all()) if "paper_id" in df else False,
            "observed": int(df["paper_id"].isna().sum()) if "paper_id" in df else total_rows,
        },
        {
            # Duplicate id làm retrieval_hit_rate và repair comparison bị sai lệch.
            "name": "paper_id_unique",
            "passed": bool(df["paper_id"].is_unique) if "paper_id" in df else False,
            "observed": int(df["paper_id"].duplicated().sum()) if "paper_id" in df else total_rows,
        },
        {
            # Title rỗng làm exact lookup trong câu hỏi đánh giá không hoạt động.
            "name": "title_not_blank",
            "passed": bool(df["title"].fillna("").str.strip().ne("").all()) if "title" in df else False,
            "observed": int(df["title"].fillna("").str.strip().eq("").sum()) if "title" in df else total_rows,
        },
        {
            # Summary ngắn/rỗng thường là dấu hiệu record không đủ nội dung để embed.
            "name": "summary_min_40_chars",
            "passed": bool((df["summary"].fillna("").str.len() >= 40).all()) if "summary" in df else False,
            "observed": int((df["summary"].fillna("").str.len() < 40).sum()) if "summary" in df else total_rows,
        },
        {
            # age_days vượt threshold nghĩa là nguồn dữ liệu đã stale so với yêu cầu lab.
            "name": "freshness_threshold",
            "passed": bool((pd.to_numeric(df["age_days"], errors="coerce") <= settings.freshness_threshold_days).all())
            if "age_days" in df
            else False,
            "observed": int((pd.to_numeric(df["age_days"], errors="coerce") > settings.freshness_threshold_days).sum())
            if "age_days" in df
            else total_rows,
            "threshold_days": settings.freshness_threshold_days,
        },
    ]
    payload = {
        # success là cờ tổng hợp để report markdown có thể ghi ngắn gọn pass/fail.
        "report_name": report_name,
        "total_rows": total_rows,
        "passed_checks": sum(1 for check in checks if check["passed"]),
        "failed_checks": sum(1 for check in checks if not check["passed"]),
        "success": all(check["passed"] for check in checks),
        "checks": checks,
    }
    write_json(settings.paths.quality_dir / f"{report_name}.json", payload)
    return payload


def build_freshness_report(df: pd.DataFrame, settings: Settings, report_path) -> dict[str, Any]:
    """Summarize publication freshness and persist the report."""
    # Parse lại bằng pandas để report không phụ thuộc kiểu dữ liệu hiện tại của cột
    # published, vì CSV load lại thường biến ngày thành string.
    published = pd.to_datetime(df["published"], errors="coerce", utc=True) if "published" in df else pd.Series(dtype="datetime64[ns, UTC]")
    age_days = pd.to_numeric(df["age_days"], errors="coerce") if "age_days" in df else pd.Series(dtype="float64")
    stale_mask = age_days > settings.freshness_threshold_days
    payload = {
        # latest/oldest giúp người đọc thấy dữ liệu có thật sự mới hay không,
        # không chỉ nhìn một cờ boolean is_fresh.
        "latest_published": published.max().date().isoformat() if not published.dropna().empty else None,
        "oldest_published": published.min().date().isoformat() if not published.dropna().empty else None,
        "stale_rows": int(stale_mask.sum()) if not age_days.empty else 0,
        "total_rows": int(len(df)),
        "freshness_threshold_days": settings.freshness_threshold_days,
        "is_fresh": bool(len(df) > 0 and int(stale_mask.sum()) == 0),
    }
    write_json(report_path, payload)
    return payload
