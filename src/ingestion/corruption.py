from __future__ import annotations

from datetime import timedelta

import pandas as pd

from core.utils import normalize_whitespace, write_json


def _refresh_embedding_text(df: pd.DataFrame) -> pd.DataFrame:
    # Sau khi làm hỏng title/summary/date, phải build lại các cột phụ để index
    # phản ánh đúng dữ liệu đã bị corrupt, không vô tình dùng text sạch cũ.
    df = df.copy()
    df["summary_chars"] = df["summary"].fillna("").astype(str).str.len()
    df["text_for_embedding"] = df.apply(
        lambda row: normalize_whitespace(
            " ".join(
                [
                    f"Title: {row.get('title', '')}.",
                    f"Summary: {row.get('summary', '')}",
                    f"Authors: {row.get('authors_joined', '')}.",
                    f"Categories: {row.get('categories_joined', '')}.",
                    f"Published: {row.get('published', '')}.",
                ]
            )
        ),
        axis=1,
    )
    return df


def corrupt_clean_dataframe(df: pd.DataFrame, output_log_path) -> pd.DataFrame:
    """Simulate realistic data corruption and write an operation log."""
    if df.empty:
        raise ValueError("Cannot corrupt an empty dataframe.")

    corrupted = df.copy().reset_index(drop=True)
    log: list[dict] = []

    # Xóa một phần record mới nhất để mô phỏng ingestion bị thiếu dữ liệu gần đây.
    # Vì cleaning đã sort mới nhất trước, head() chính là nhóm dễ ảnh hưởng freshness nhất.
    drop_count = max(1, len(corrupted) // 8)
    dropped_ids = corrupted.head(drop_count)["paper_id"].tolist()
    corrupted = corrupted.iloc[drop_count:].reset_index(drop=True)
    log.append({"operation": "drop_latest_records", "count": drop_count, "paper_ids": dropped_ids})

    if not corrupted.empty:
        # Blank summary tạo lỗi rõ ràng cho quality check và làm câu hỏi summary
        # dễ trả lời sai hơn.
        blank_count = max(1, len(corrupted) // 6)
        blank_indexes = corrupted.index[:blank_count].tolist()
        corrupted.loc[blank_indexes, "summary"] = ""
        log.append({"operation": "blank_summary", "count": blank_count, "indexes": blank_indexes})

    if len(corrupted) > 1:
        # Noise làm embedding kém chính xác nhưng vẫn giữ row tồn tại, giống lỗi
        # dữ liệu bị lẫn telemetry/log/HTML rác.
        noise_indexes = corrupted.index[1 : 1 + max(1, len(corrupted) // 6)].tolist()
        corrupted.loc[noise_indexes, "summary"] = (
            corrupted.loc[noise_indexes, "summary"].fillna("").astype(str)
            + " IRRELEVANT_NOISE " * 12
            + " unrelated duplicated telemetry"
        )
        log.append({"operation": "inject_noise", "count": len(noise_indexes), "indexes": noise_indexes})

    if len(corrupted) > 2:
        # Truncate title làm exact lookup theo title yếu đi, từ đó kiểm tra agent có
        # chịu ảnh hưởng khi metadata quan trọng bị cắt cụt hay không.
        title_indexes = corrupted.index[2 : 2 + max(1, len(corrupted) // 8)].tolist()
        corrupted.loc[title_indexes, "title"] = corrupted.loc[title_indexes, "title"].astype(str).str.slice(0, 24)
        log.append({"operation": "truncate_title", "count": len(title_indexes), "indexes": title_indexes})

    if len(corrupted) > 3:
        # Đẩy ngày publish lùi 2 năm để freshness report nhìn thấy stale rows rõ ràng.
        stale_indexes = corrupted.tail(max(1, len(corrupted) // 6)).index.tolist()
        stale_dates = pd.to_datetime(corrupted.loc[stale_indexes, "published"], errors="coerce")
        corrupted.loc[stale_indexes, "published"] = [
            (date - timedelta(days=730)).date().isoformat() if not pd.isna(date) else "2000-01-01"
            for date in stale_dates
        ]
        corrupted.loc[stale_indexes, "age_days"] = pd.to_numeric(corrupted.loc[stale_indexes, "age_days"], errors="coerce").fillna(0) + 730
        log.append({"operation": "make_stale", "count": len(stale_indexes), "indexes": stale_indexes})

    # Duplicate paper_id là lỗi dữ liệu phổ biến trong ETL; quality check phải bắt được.
    duplicate_count = min(2, len(corrupted))
    if duplicate_count:
        duplicates = corrupted.tail(duplicate_count).copy()
        corrupted = pd.concat([corrupted, duplicates], ignore_index=True)
        log.append({"operation": "add_duplicates", "count": duplicate_count, "paper_ids": duplicates["paper_id"].tolist()})

    corrupted = _refresh_embedding_text(corrupted)
    write_json(output_log_path, log)
    return corrupted
