from __future__ import annotations

import pandas as pd

from core.config import load_settings
from core.utils import now_utc, read_json, write_csv, write_json
from evaluation.metrics import evaluate_pipeline
from ingestion.cleaning import build_clean_dataframe
from ingestion.corruption import corrupt_clean_dataframe
from ingestion.crossref import load_raw_records
from observability.quality import build_freshness_report, run_data_quality_checks
from observability.reporting import generate_corruption_report
from pipelines.phase1 import main as run_phase1
from retrieval.index import LocalEmbeddingIndex


def _save_dataframe(df: pd.DataFrame, csv_path, json_path) -> None:
    # Giữ cùng convention artifact với phase1 để người chấm dễ đối chiếu
    # baseline/corrupted/repaired.
    write_csv(df, csv_path)
    write_json(json_path, df.fillna("").to_dict(orient="records"))


def main() -> None:
    """Run corruption, repaired rebuild, evaluation, and comparison reporting."""
    settings = load_settings()
    # Corruption flow phụ thuộc baseline clean data, metrics và test set. Nếu người dùng
    # chạy thẳng script này trước, tự động dựng baseline để không bị thiếu artifact.
    if not settings.paths.clean_csv.exists() or not settings.paths.baseline_metrics.exists() or not settings.paths.eval_testset.exists():
        run_phase1()

    # Baseline metrics được giữ nguyên để comparison dùng cùng mốc ban đầu.
    baseline_metrics = read_json(settings.paths.baseline_metrics)
    clean_df = pd.read_csv(settings.paths.clean_csv)

    # Bước corrupted: cố ý làm hỏng clean dataset, build lại index, rồi đánh giá trên
    # chính test set cũ để đo impact công bằng.
    corrupted_df = corrupt_clean_dataframe(clean_df, output_log_path=settings.paths.corruption_log)
    _save_dataframe(corrupted_df, settings.paths.corrupted_clean_csv, settings.paths.corrupted_clean_json)
    corrupted_index = LocalEmbeddingIndex.build(
        corrupted_df,
        settings=settings,
        embeddings_output_path=settings.paths.corrupted_embeddings_json,
    )
    corrupted_eval = evaluate_pipeline(
        settings=settings,
        index=corrupted_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.corrupted_metrics,
        answers_output_path=settings.paths.corrupted_answers,
    )
    corrupted_quality = run_data_quality_checks(corrupted_df, settings=settings, report_name="corrupted_quality")
    corrupted_freshness = build_freshness_report(
        corrupted_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "corrupted_freshness_report.json",
    )

    # Bước repaired: không sửa từng lỗi thủ công, mà rebuild từ raw snapshot để mô phỏng
    # cách repair ETL đúng hơn trong thực tế.
    raw_records = load_raw_records(settings.paths.raw_records_json)
    repaired_df = build_clean_dataframe(raw_records, run_date=now_utc())
    _save_dataframe(repaired_df, settings.paths.repaired_clean_csv, settings.paths.repaired_clean_json)
    repaired_index = LocalEmbeddingIndex.build(
        repaired_df,
        settings=settings,
        embeddings_output_path=settings.paths.repaired_embeddings_json,
    )
    repaired_eval = evaluate_pipeline(
        settings=settings,
        index=repaired_index,
        test_set_path=settings.paths.eval_testset,
        metrics_output_path=settings.paths.repaired_metrics,
        answers_output_path=settings.paths.repaired_answers,
    )
    repaired_quality = run_data_quality_checks(repaired_df, settings=settings, report_name="repaired_quality")
    repaired_freshness = build_freshness_report(
        repaired_df,
        settings=settings,
        report_path=settings.paths.quality_dir / "repaired_freshness_report.json",
    )

    # Report cuối chỉ đọc các payload đã tạo, tránh tính lại số liệu khác với artifact.
    generate_corruption_report(
        settings.paths.comparison_report,
        baseline_metrics=baseline_metrics,
        corrupted_metrics=corrupted_eval.summary,
        repaired_metrics=repaired_eval.summary,
        corrupted_quality=corrupted_quality,
        repaired_quality=repaired_quality,
        corrupted_freshness=corrupted_freshness,
        repaired_freshness=repaired_freshness,
    )
    print(f"Corruption flow complete: {settings.paths.comparison_report}")
