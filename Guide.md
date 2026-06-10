# Guide

## Tổng quan

Bài lab này mô phỏng một data pipeline nhỏ cho hệ thống RAG. Các bạn sẽ đi qua 2 pha:

1. Xây baseline pipeline với dữ liệu sạch
2. Giả lập dữ liệu lỗi, đo impact lên agent, sau đó repair và so sánh

## Bước 1: Cài môi trường

1. Di chuyển vào root project
2. Tạo file `.env` nếu cần
3. Cài dependency:

```bash
uv sync
```

Hoặc dùng `pip`:

```bash
pip install -r requirements.txt
```

## Bước 2: Hiểu cấu trúc code

- `src/core/config.py`: nơi chứa path và settings
- `src/ingestion/crossref.py`: load dữ liệu raw từ source
- `src/ingestion/cleaning.py`: clean và tạo bảng dữ liệu
- `src/retrieval/index.py`: embedding + ChromaDB
- `src/retrieval/agent.py`: RAG agent
- `src/evaluation/metrics.py`: chấm điểm
- `src/observability/quality.py`: data quality và freshness
- `src/pipelines/phase1.py`: baseline flow
- `src/pipelines/corruption_flow.py`: corruption flow

## Bước 3: Load raw data từ source

CROSSREF_API_URL = "https://api.crossref.org/works"
Cần hoàn thành:

- `src/ingestion/crossref.py`

Yêu cầu:

- Gọi external source để lấy danh sách paper
- Parse response thành record schema nhất quán
- Lưu raw response vào `data/raw/`
- Lưu raw records đã parse vào `data/raw/`

Sau khi xong, em nên tự trả lời:

- Source nào đang được dùng?
- Query/filter là gì?
- Record schema gồm những trường nào?

## Bước 4: Làm sạch dữ liệu

Cần hoàn thành:

- `src/ingestion/cleaning.py`

Yêu cầu:

- Remove record không hợp lệ
- Chuẩn hóa title, summary, authors, categories
- Tạo cột `text_for_embedding`
- Tính freshness fields như `published`, `age_days`
- Lưu cleaned data vào `data/clean/`

## Bước 5: Tạo evaluation set

Cần hoàn thành:

- `src/evaluation/testset.py`

Yêu cầu:

- Tạo bộ câu hỏi từ cleaned dataset
- Mỗi sample cần có `question`, `ground_truth`, `ground_truth_doc_ids`, `question_type`

## Bước 6: Tạo embedding và vector store

Phần này đã có code tham khảo ở:

- `src/retrieval/embeddings.py`
- `src/retrieval/index.py`

Cần đọc kỹ:

- Cách dùng `sentence-transformers/all-MiniLM-L6-v2`
- Cách tạo collection trong ChromaDB
- Cách query top-k context

## Bước 7: Cấu hình LLM provider

Phần này đã có code tham khảo ở:

- `src/retrieval/llm.py`

Provider cần support:

- OpenAI
- Gemini
- Anthropic
- OpenRouter
- Ollama
- Custom OpenAI-compatible endpoint

Nhiệm vụ của em:

- Đọc code
- Hiểu `LLM_PROVIDER`, `LLM_MODEL` và các API key được map như thế nào

## Bước 8: Chạy agent

Phần agent đã có code tham khảo ở:

- `src/retrieval/agent.py`
- `src/retrieval/qa.py`

Sau khi ETL và index xong, agent có thể:

- Semantic search trong local corpus
- Lookup theo `paper_id` hoặc exact title
- Trả lời câu hỏi factual

## Bước 9: Chạy baseline pipeline

Cần hoàn thành:

- `src/pipelines/phase1.py`

Pipeline baseline cần:

1. Load/fetch raw records
2. Clean data
3. Build embedding index
4. Tạo hoặc load test set
5. Evaluate
6. Run data quality checks
7. Tạo freshness report
8. Tạo report markdown

Sau khi code xong, chạy:

```bash
uv run python script/run_phase1.py
```

Cần kiểm tra output trong:

- `data/clean/`
- `data/embeddings/`
- `data/eval/`
- `data/results/`
- `data/quality/`
- `data/reports/`

## Bước 10: Đọc score

Cần đọc file:

- `data/results/baseline_metrics.json`

Chỉ số cần quan tâm:

- `retrieval_hit_rate`
- `mean_token_f1`
- `judge_accuracy`
- `mean_judge_score`
- `ragas`

## Bước 11: Tạo data quality report

Cần hoàn thành:

- `src/observability/quality.py`
- `src/observability/reporting.py`

Yêu cầu tối thiểu:

- Data quality checks
- Freshness monitoring
- Markdown report

## Bước 12: Corrupt dữ liệu

Cần hoàn thành:

- `src/ingestion/corruption.py`
- `src/pipelines/corruption_flow.py`

Ý tưởng corruption:

- Xóa một số latest records
- Blank summary
- Add noise vào summary
- Truncate title
- Làm stale publication date
- Add duplicate rows

## Bước 13: Re-evaluate sau corruption

Flow corruption cần:

1. Đọc cleaned baseline
2. Tạo corrupted dataset
3. Rebuild embedding
4. Evaluate trên test set cũ
5. Run quality checks
6. Tạo freshness report
7. Repair lại từ raw source
8. Evaluate lại lần nữa
9. Tạo comparison report

Chạy:

```bash
uv run python script/run_corruption_flow.py
```

## Bước 14: So sánh baseline, corrupted, repaired

Cần so sánh:

- Retrieval hit rate
- Token F1
- Judge accuracy
- Mean judge score
- Data quality success/fail
- Freshness status

Mục tiêu là chứng minh:

- Dữ liệu xấu làm giảm performance của agent
- Repair đúng cách sẽ phục hồi performance

## Bước 15: Tự review trước khi nộp

Checklist:

- Code có chia module rõ ràng không?
- Raw/clean/eval/results được lưu đầy đủ không?
- Agent có chạy được không?
- Metrics có hợp lý không?
- Report markdown có đọc được không?
- Có chứng minh được impact của corruption không?
