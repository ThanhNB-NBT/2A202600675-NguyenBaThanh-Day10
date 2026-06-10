from __future__ import annotations

from typing import Any

from core.utils import write_text


def _metric_line(name: str, payload: dict[str, Any], key: str) -> str:
    # Helper nhỏ để các metric dạng float luôn được format nhất quán trong bảng Markdown.
    value = payload.get(key, "n/a")
    if isinstance(value, float):
        value = f"{value:.4f}"
    return f"| {name} | {value} |"


def generate_phase1_report(
    report_path,
    source_summary: dict[str, Any],
    metrics: dict[str, Any],
    quality: dict[str, Any],
    freshness: dict[str, Any],
) -> None:
    """Write the baseline markdown report."""
    # Report baseline cố tình lấy dữ liệu từ payload đã lưu/tính ở pipeline,
    # không đọc trực tiếp dataframe, để nội dung report khớp artifact thực tế.
    lines = [
        "# Phase 1 Baseline Report",
        "",
        "## Source",
        "",
        f"- Source: {source_summary.get('source_api', 'n/a')}",
        f"- Query: {source_summary.get('source_query', 'n/a')}",
        f"- Filter: {source_summary.get('source_filter', 'n/a')}",
        f"- Raw records: {source_summary.get('raw_records', 'n/a')}",
        f"- Clean records: {source_summary.get('clean_records', 'n/a')}",
        "",
        "## Evaluation Metrics",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        _metric_line("Samples", metrics, "samples"),
        _metric_line("Retrieval hit rate", metrics, "retrieval_hit_rate"),
        _metric_line("Mean token F1", metrics, "mean_token_f1"),
        _metric_line("Judge accuracy", metrics, "judge_accuracy"),
        _metric_line("Mean judge score", metrics, "mean_judge_score"),
        "",
        "## Data Quality",
        "",
        f"- Success: {quality.get('success')}",
        f"- Passed checks: {quality.get('passed_checks')}",
        f"- Failed checks: {quality.get('failed_checks')}",
        "",
        "## Freshness",
        "",
        f"- Latest published: {freshness.get('latest_published')}",
        f"- Oldest published: {freshness.get('oldest_published')}",
        f"- Stale rows: {freshness.get('stale_rows')} / {freshness.get('total_rows')}",
        f"- Fresh: {freshness.get('is_fresh')}",
        "",
    ]
    write_text(report_path, "\n".join(lines))


def generate_corruption_report(
    report_path,
    baseline_metrics: dict[str, Any],
    corrupted_metrics: dict[str, Any],
    repaired_metrics: dict[str, Any],
    corrupted_quality: dict[str, Any],
    repaired_quality: dict[str, Any],
    corrupted_freshness: dict[str, Any],
    repaired_freshness: dict[str, Any],
) -> None:
    """Write the corruption comparison markdown report."""
    rows = []
    # Dùng cùng danh sách metric cho baseline/corrupted/repaired để người đọc thấy
    # impact của dữ liệu lỗi và mức phục hồi sau repair ngay trong một bảng.
    for key, label in [
        ("samples", "Samples"),
        ("retrieval_hit_rate", "Retrieval hit rate"),
        ("mean_token_f1", "Mean token F1"),
        ("judge_accuracy", "Judge accuracy"),
        ("mean_judge_score", "Mean judge score"),
    ]:
        values = [baseline_metrics.get(key, "n/a"), corrupted_metrics.get(key, "n/a"), repaired_metrics.get(key, "n/a")]
        formatted = [f"{value:.4f}" if isinstance(value, float) else str(value) for value in values]
        rows.append(f"| {label} | {formatted[0]} | {formatted[1]} | {formatted[2]} |")

    lines = [
        "# Corruption Impact Report",
        "",
        "## Metrics Comparison",
        "",
        "| Metric | Baseline | Corrupted | Repaired |",
        "| --- | ---: | ---: | ---: |",
        *rows,
        "",
        "## Quality Comparison",
        "",
        f"- Corrupted quality success: {corrupted_quality.get('success')} ({corrupted_quality.get('failed_checks')} failed checks)",
        f"- Repaired quality success: {repaired_quality.get('success')} ({repaired_quality.get('failed_checks')} failed checks)",
        "",
        "## Freshness Comparison",
        "",
        f"- Corrupted stale rows: {corrupted_freshness.get('stale_rows')} / {corrupted_freshness.get('total_rows')}",
        f"- Repaired stale rows: {repaired_freshness.get('stale_rows')} / {repaired_freshness.get('total_rows')}",
        "",
        "## Interpretation",
        "",
        "Corruption is expected to reduce retrieval or answer quality because records are removed, duplicated, blanked, noised, and made stale.",
        "Repair rebuilds the clean dataset from the raw source snapshot, then rebuilds the index and evaluation artifacts.",
        "",
    ]
    write_text(report_path, "\n".join(lines))
