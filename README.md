# Day 10 - Data Pipeline And Data Observability

Chào các bạn đến với bài lab Day 10.

Mục tiêu của bài này là xây dựng một ETL pipeline nhỏ nhưng đầy đủ cho một hệ thống RAG:

- Lấy dữ liệu học thuật từ nguồn bên ngoài
- Làm sạch và chuẩn hóa thành cleaned dataset
- Tạo embedding và nạp vào ChromaDB
- Xây agent để trả lời câu hỏi trên bộ dữ liệu
- Đánh giá chất lượng của agent trước và sau khi dữ liệu bị corrupt
- Tạo báo cáo data quality, freshness và metrics comparison

Cấu trúc chính:

- `src/core/`: config và utility dùng chung
- `src/ingestion/`: load source, clean, corrupt data
- `src/retrieval/`: embeddings, vector store, LLM providers, agent
- `src/evaluation/`: test set và scoring
- `src/observability/`: quality checks, freshness, reports
- `src/pipelines/`: flow baseline và flow corruption
- `script/`: entrypoint để chạy lab
- `data/`: nơi chứa artifact đầu ra

Tài liệu hướng dẫn:

- [Guide.md](Guide.md)
- [Rubric.md](Rubric.md)

Gợi ý cách bắt đầu:

```bash
uv sync
uv run python script/run_phase1.py
```

Nếu dùng `pip` thay vì `uv`, các bạn có thể cài bằng:

```bash
pip install -r requirements.txt
```

Nếu code chưa chạy được thì đó là bình thường. Các bạn cần hoàn thành các file pseudo-code trước, sau đó mới có thể chạy end-to-end.
