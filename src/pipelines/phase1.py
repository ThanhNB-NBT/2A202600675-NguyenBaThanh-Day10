from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from evaluation.testset import build_test_set
from ingestion.cleaning import build_clean_dataframe
from ingestion.crossref import fetch_source_records, load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_phase1_report
from retrieval.index import LocalEmbeddingIndex
from retrieval.qa import answer_question


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    # Lưu cả CSV và JSON: CSV dễ mở bằng Excel, JSON giữ cấu trúc list/dict tốt hơn
    # cho các bước hoặc tool khác đọc lại.
    write_csv(df, csv_path)
    write_json(json_path, df.fillna("").to_dict(orient="records"))


def main() -> None:
    """Run the baseline ETL, index, evaluation, quality, and report flow."""
    settings = load_settings()
    # Mặc định ưu tiên snapshot đã có để lần chạy sau không phụ thuộc network.
    # Muốn fetch mới từ Crossref thì set REFRESH_SOURCE=1 trong .env.
    if settings.paths.raw_records_json.exists() and not settings.refresh_source:
        records = load_raw_records(settings.paths.raw_records_json)
    else:
        records = fetch_source_records(settings)

    # Cleaning là ranh giới giữa dữ liệu raw và dữ liệu dùng cho RAG.
    # Mọi artifact phía sau nên đọc clean_df thay vì tự parse raw lần nữa.
    clean_df = build_clean_dataframe(records, run_date=now_utc())
    _save_dataframe(clean_df, settings.paths.clean_csv, settings.paths.clean_json)

    # Build Chroma index từ text_for_embedding và lưu manifest để có thể load lại.
    index = LocalEmbeddingIndex.build(clean_df, settings=settings, embeddings_output_path=settings.paths.embeddings_json)

    # Test set cũng được cache để baseline/corrupted/repaired so sánh trên cùng bộ câu hỏi.
    if settings.paths.eval_testset.exists() and not settings.refresh_test_set:
        test_set = read_json(settings.paths.eval_testset)
    else:
        test_set = build_test_set(clean_df, settings.paths.eval_testset)

    # evaluate_pipeline sinh cả metrics tổng hợp lẫn từng câu trả lời để debug khi điểm giảm.
    evaluation = evaluate_pipeline(
        settings=settings,
        index=index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.baseline_metrics,
        answers_output_path=settings.paths.baseline_answers,
    )
    quality = run_data_quality_checks(clean_df, settings=settings, report_name="baseline_quality")
    freshness = build_freshness_report(clean_df, settings=settings, report_path=settings.paths.freshness_report)

    # Demo answers là vài ví dụ nhanh để người chấm mở artifact thấy agent trả lời thế nào.
    demo_answers = []
    for item in test_set[: min(3, len(test_set))]:
        result = answer_question(item["question"], settings=settings, index=index)
        demo_answers.append(
            {
                "question": item["question"],
                "answer": result.answer,
                "retrieved_doc_ids": result.retrieved_doc_ids,
                "retrieved_titles": result.retrieved_titles,
            }
        )
    write_json(settings.paths.demo_answers, demo_answers)

    # Source summary gom metadata của lần chạy để markdown report không bị tách rời
    # khỏi query/filter thực tế đã dùng.
    source_summary = {
        "source_api": settings.source_api,
        "source_query": settings.source_query,
        "source_filter": settings.source_filter,
        "raw_records": len(records),
        "clean_records": len(clean_df),
    }
    generate_phase1_report(
        settings.paths.baseline_report,
        source_summary=source_summary,
        metrics=evaluation.summary,
        quality=quality,
        freshness=freshness,
    )
    print(f"Baseline pipeline complete: {settings.paths.baseline_report}")
