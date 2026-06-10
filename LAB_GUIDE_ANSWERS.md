# Ghi chú và câu trả lời lab Day 10

File này tổng hợp câu trả lời cho `Guide.md`, giải thích cấu trúc code, các artifact đầu ra và kiến thức chính của lab Data Pipeline, Data Observability và RAG evaluation.

## 1. Mục tiêu của lab

Lab mô phỏng một pipeline dữ liệu nhỏ cho hệ thống RAG dùng dữ liệu học thuật từ Crossref.

Pipeline có hai pha chính:

1. Pha baseline: lấy dữ liệu sạch, chuẩn hóa, tạo embedding, build ChromaDB index, tạo bộ câu hỏi đánh giá, chạy evaluation và sinh report.
2. Pha corruption: cố ý làm hỏng dữ liệu, đo ảnh hưởng lên retrieval/answer quality, repair lại từ raw source, rồi so sánh baseline, corrupted và repaired.

Mục tiêu quan trọng nhất là chứng minh rằng chất lượng dữ liệu ảnh hưởng trực tiếp đến chất lượng agent RAG. Khi dữ liệu bị thiếu, trùng, stale, blank summary hoặc nhiễu, retrieval và câu trả lời sẽ giảm chất lượng. Khi repair đúng cách từ raw source, metrics có thể phục hồi.

## 2. Cấu trúc project

```text
src/core/
  config.py       Cấu hình đường dẫn, provider LLM, query Crossref, threshold freshness.
  utils.py        Hàm tiện ích đọc/ghi JSON, CSV, normalize text, thời gian UTC.

src/ingestion/
  crossref.py     Gọi Crossref API, parse raw payload thành PaperRecord.
  cleaning.py     Làm sạch raw records thành dataframe dùng cho embedding.
  corruption.py   Cố ý tạo dữ liệu lỗi để đo impact.

src/retrieval/
  embeddings.py   MiniLM embedding, có fallback hash embedding khi thiếu model cache.
  index.py        Build/load ChromaDB index và query top-k context.
  llm.py          Cấu hình nhiều LLM provider.
  agent.py        Agent có tool semantic search và lookup paper.
  qa.py           QA heuristic cho câu hỏi factual trên corpus đã index.

src/evaluation/
  testset.py      Tạo bộ câu hỏi đánh giá từ cleaned dataset.
  metrics.py      Chạy evaluation, tính retrieval hit rate, token F1, judge score.

src/observability/
  quality.py      Data quality checks và freshness report.
  reporting.py    Sinh Markdown report cho baseline và corruption comparison.

src/pipelines/
  phase1.py             Baseline pipeline end-to-end.
  corruption_flow.py    Corruption, repair và comparison pipeline.

script/
  run_phase1.py            Entrypoint chạy baseline.
  run_corruption_flow.py   Entrypoint chạy corruption flow.

data/
  raw/         Raw Crossref response và raw records đã parse.
  clean/       Cleaned CSV/JSON cho baseline, corrupted, repaired.
  embeddings/  Manifest embedding/index.
  eval/        Test set.
  results/     Metrics, answers, corruption log.
  quality/     Quality/freshness reports.
  reports/     Markdown reports.
```

## 3. Câu trả lời cho Guide.md

### Bước 1. Cài môi trường

Lệnh cài dependency:

```powershell
uv sync
```

Trong môi trường Windows này có thể dùng cache riêng để tránh lỗi cache global:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv sync
```

Nếu không dùng `uv`, có thể cài bằng:

```powershell
pip install -r requirements.txt
```

### Bước 2. Hiểu cấu trúc code

Project được chia theo đúng pipeline:

- `core`: cấu hình và utility.
- `ingestion`: lấy, clean và corrupt dữ liệu.
- `retrieval`: embedding, ChromaDB, agent và QA.
- `evaluation`: tạo test set và chấm điểm.
- `observability`: kiểm tra data quality, freshness và sinh report.
- `pipelines`: ghép các module thành flow chạy end-to-end.
- `script`: file entrypoint để chạy từ terminal.

### Bước 3. Load raw data từ source

Source đang dùng:

```text
Crossref REST API
https://api.crossref.org/works
```

Query đang dùng:

```text
agentic retrieval augmented generation large language model
```

Filter đang dùng:

```text
from-pub-date:<ngày hiện tại - 180 ngày>,has-abstract:true
```

Ví dụ khi chạy ngày 2026-06-10, filter sẽ gần dạng:

```text
from-pub-date:2025-12-12,has-abstract:true
```

Số lượng record tối đa:

```text
24
```

Raw artifacts được lưu tại:

- `data/raw/crossref_response.json`: response gốc từ Crossref.
- `data/raw/crossref_records.json`: danh sách record đã parse về schema ổn định.

Schema `PaperRecord` gồm:

| Trường | Ý nghĩa |
| --- | --- |
| `paper_id` | ID nội bộ, dùng DOI dạng `doi:<doi lower-case>`. |
| `title` | Tiêu đề paper. |
| `summary` | Abstract đã làm sạch tag XML/JATS. |
| `authors` | Danh sách tác giả. |
| `categories` | Danh sách subject/category từ Crossref. |
| `primary_category` | Category chính, lấy phần tử đầu tiên hoặc fallback. |
| `published` | Ngày xuất bản dạng ISO `YYYY-MM-DD`. |
| `updated` | Ngày update/deposit fallback từ Crossref. |
| `abs_url` | URL trang paper trên Crossref/DOI. |
| `pdf_url` | PDF URL nếu Crossref có cung cấp. |
| `comment` | Subtitle/comment nếu có. |

### Bước 4. Làm sạch dữ liệu

File chính:

```text
src/ingestion/cleaning.py
```

Các việc đã làm:

- Normalize `title`, `summary`, `authors`, `categories`.
- Loại record thiếu `paper_id`, `title`, `summary` hoặc ngày publish.
- Parse ngày bằng pandas, ép về UTC để tính `age_days` nhất quán.
- Tạo các cột tiện ích:
  - `authors_joined`
  - `categories_joined`
  - `summary_chars`
  - `text_for_embedding`
- Loại duplicate theo `paper_id`.
- Loại summary quá ngắn dưới 40 ký tự.
- Sort paper mới nhất trước.
- Lưu cleaned dataset vào:
  - `data/clean/papers_clean.csv`
  - `data/clean/papers_clean.json`

`text_for_embedding` được ghép từ title, summary, authors, categories và published date. Lý do là embedding nên chứa cả nội dung chính và metadata quan trọng để semantic search có nhiều tín hiệu hơn.

### Bước 5. Tạo evaluation set

File chính:

```text
src/evaluation/testset.py
```

Bộ test được tạo từ cleaned dataset và lưu tại:

```text
data/eval/test_set.json
```

Mỗi sample có các trường:

| Trường | Ý nghĩa |
| --- | --- |
| `id` | ID câu hỏi, ví dụ `q001`. |
| `question_type` | Loại câu hỏi: `summary`, `authors`, `date`, `categories`. |
| `question` | Câu hỏi đưa vào agent/retrieval. |
| `ground_truth` | Đáp án chuẩn lấy từ cleaned dataframe. |
| `ground_truth_doc_ids` | Paper ID đúng, dùng để tính retrieval hit. |

Cách tạo câu hỏi:

- Chọn tối đa 8 paper mới nhất.
- Xoay vòng 4 loại câu hỏi.
- Đặt title trong dấu nháy để `retrieval.qa` có thể lookup exact title trước khi fallback sang semantic search.

### Bước 6. Tạo embedding và vector store

Files chính:

```text
src/retrieval/embeddings.py
src/retrieval/index.py
```

Embedding model chính:

```text
sentence-transformers/all-MiniLM-L6-v2
```

Vector store:

```text
ChromaDB PersistentClient
```

Các artifact liên quan:

- `data/chroma/`: database ChromaDB persist trên disk.
- `data/embeddings/papers_embeddings.json`: manifest cho baseline index.
- `data/embeddings/papers_embeddings_corrupted.json`: manifest cho corrupted index.
- `data/embeddings/papers_embeddings_repaired.json`: manifest cho repaired index.

Luồng build index:

1. Convert dataframe thành list documents.
2. Mỗi document có:
   - `record_id`
   - `paper_id`
   - `title`
   - `content`
   - `metadata`
3. Embed `content`.
4. Tạo Chroma collection.
5. Add ids, embeddings, documents và metadata vào collection.
6. Lưu manifest để load lại.

Nếu MiniLM không có trong cache local hoặc môi trường không có network, code có fallback hash embedding deterministic. Fallback này giúp pipeline vẫn chạy được end-to-end trong môi trường chấm, dù chất lượng semantic embedding không bằng MiniLM thật.

### Bước 7. Cấu hình LLM provider

File chính:

```text
src/retrieval/llm.py
src/core/config.py
```

Các provider được support:

| Provider | Env cần dùng |
| --- | --- |
| Gemini | `LLM_PROVIDER=gemini`, `GOOGLE_API_KEY` |
| OpenAI | `LLM_PROVIDER=openai`, `OPENAI_API_KEY` |
| Anthropic | `LLM_PROVIDER=anthropic`, `ANTHROPIC_API_KEY` |
| OpenRouter | `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, `OPENROUTER_BASE_URL` |
| Ollama | `LLM_PROVIDER=ollama`, `OLLAMA_BASE_URL` |
| Custom OpenAI-compatible | `LLM_PROVIDER=custom`, `CUSTOM_LLM_BASE_URL`, `CUSTOM_LLM_API_KEY` |

Model mặc định:

```text
gemini-2.5-flash
```

File `.env.example` đã có sẵn biến môi trường mẫu. Không hardcode API key trong code.

Lưu ý: Evaluation hiện tại có fallback heuristic judge nên vẫn chạy được khi không có API key LLM. Nếu bật LLM thật, judge có thể dùng model để đánh giá câu trả lời.

### Bước 8. Chạy agent

Files chính:

```text
src/retrieval/agent.py
src/retrieval/qa.py
```

Agent có thể:

- Semantic search trong corpus local.
- Lookup theo `paper_id`.
- Lookup theo exact title.
- Trả lời các câu hỏi factual về summary, authors, date, categories.

Trong `qa.py`, logic trả lời được tối ưu cho lab:

- Câu hỏi tác giả trả về `authors_joined`.
- Câu hỏi ngày publish trả về `published`.
- Câu hỏi category trả về `categories_joined`.
- Câu hỏi summary trả về câu đầu tiên của `summary`.

### Bước 9. Chạy baseline pipeline

File chính:

```text
src/pipelines/phase1.py
```

Lệnh chạy:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv run python script/run_phase1.py
```

Các bước trong baseline pipeline:

1. Load settings.
2. Nếu đã có raw snapshot thì load từ `data/raw/crossref_records.json`.
3. Nếu chưa có snapshot hoặc `REFRESH_SOURCE=1`, fetch Crossref API.
4. Clean data.
5. Lưu clean CSV/JSON.
6. Build Chroma index.
7. Tạo hoặc load test set.
8. Evaluate.
9. Chạy data quality checks.
10. Tạo freshness report.
11. Tạo demo answers.
12. Tạo Markdown report.

Output cần kiểm tra:

- `data/clean/papers_clean.csv`
- `data/clean/papers_clean.json`
- `data/embeddings/papers_embeddings.json`
- `data/eval/test_set.json`
- `data/results/baseline_metrics.json`
- `data/results/baseline_answers.json`
- `data/results/agent_demo_answers.json`
- `data/quality/baseline_quality.json`
- `data/quality/freshness_report.json`
- `data/reports/phase1_report.md`

### Bước 10. Đọc score

File metrics:

```text
data/results/baseline_metrics.json
```

Kết quả baseline hiện tại:

| Metric | Value |
| --- | ---: |
| `samples` | 8 |
| `retrieval_hit_rate` | 1.0 |
| `mean_token_f1` | 1.0 |
| `judge_accuracy` | 1.0 |
| `mean_judge_score` | 5 |
| `ragas` | skipped nếu chưa set `RUN_RAGAS=1` |

Ý nghĩa các metric:

| Metric | Ý nghĩa |
| --- | --- |
| `retrieval_hit_rate` | Tỷ lệ câu hỏi mà top-k retrieved docs chứa document đúng. |
| `mean_token_f1` | Mức trùng token giữa answer và ground truth. |
| `judge_accuracy` | Tỷ lệ answer được judge là đúng. |
| `mean_judge_score` | Điểm judge trung bình từ 1 đến 5. |
| `ragas` | Bộ metric nâng cao của RAGAS, mặc định skip để chạy nhanh. |

### Bước 11. Tạo data quality report

Files chính:

```text
src/observability/quality.py
src/observability/reporting.py
```

Quality checks gồm:

| Check | Mục đích |
| --- | --- |
| `row_count_at_least_3` | Dataset đủ tối thiểu để evaluation có ý nghĩa. |
| `paper_id_not_null` | Paper ID không được null vì dùng để nối metrics. |
| `paper_id_unique` | Không có duplicate paper ID. |
| `title_not_blank` | Title không rỗng để lookup/evaluation hoạt động. |
| `summary_min_40_chars` | Summary đủ dài để embedding và QA có thông tin. |
| `freshness_threshold` | `age_days` không vượt quá threshold 180 ngày. |

Freshness report gồm:

- `latest_published`
- `oldest_published`
- `stale_rows`
- `total_rows`
- `freshness_threshold_days`
- `is_fresh`

Baseline quality hiện tại:

```text
passed_checks = 6
failed_checks = 0
success = true
```

### Bước 12. Corrupt dữ liệu

Files chính:

```text
src/ingestion/corruption.py
src/pipelines/corruption_flow.py
```

Các kiểu corruption đã mô phỏng:

| Kiểu corruption | Ý nghĩa |
| --- | --- |
| Drop latest records | Mô phỏng ingestion thiếu dữ liệu mới. |
| Blank summary | Mô phỏng abstract bị mất. |
| Inject noise | Mô phỏng dữ liệu bị lẫn log/telemetry/rác. |
| Truncate title | Mô phỏng metadata bị cắt cụt. |
| Make stale date | Mô phỏng publication date bị cũ đi. |
| Add duplicates | Mô phỏng ETL duplicate rows. |

Corruption log được lưu tại:

```text
data/results/corruption_log.json
```

### Bước 13. Re-evaluate sau corruption

Lệnh chạy:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv run python script/run_corruption_flow.py
```

Flow corruption:

1. Đọc baseline metrics và cleaned dataset.
2. Tạo corrupted dataframe.
3. Lưu corrupted CSV/JSON.
4. Build corrupted Chroma index.
5. Evaluate corrupted trên test set cũ.
6. Chạy quality/freshness trên corrupted data.
7. Repair bằng cách rebuild clean dataframe từ raw records.
8. Build repaired index.
9. Evaluate repaired trên cùng test set.
10. Chạy quality/freshness trên repaired data.
11. Tạo comparison report.

Artifact quan trọng:

- `data/clean/papers_clean_corrupted.csv`
- `data/clean/papers_clean_repaired.csv`
- `data/results/corrupted_metrics.json`
- `data/results/repaired_metrics.json`
- `data/quality/corrupted_quality.json`
- `data/quality/repaired_quality.json`
- `data/reports/corruption_report.md`

### Bước 14. So sánh baseline, corrupted, repaired

Kết quả hiện tại:

| Metric | Baseline | Corrupted | Repaired |
| --- | ---: | ---: | ---: |
| Samples | 8 | 8 | 8 |
| Retrieval hit rate | 1.0000 | 0.6250 | 1.0000 |
| Mean token F1 | 1.0000 | 0.6840 | 1.0000 |
| Judge accuracy | 1.0000 | 0.6250 | 1.0000 |
| Mean judge score | 5 | 3.5000 | 5 |

Quality comparison:

| Dataset | Passed checks | Failed checks | Success |
| --- | ---: | ---: | --- |
| Baseline | 6 | 0 | true |
| Corrupted | 3 | 3 | false |
| Repaired | 6 | 0 | true |

Corrupted quality fail do:

- Có 2 duplicate `paper_id`.
- Có 1 summary dưới 40 ký tự.
- Có 5 stale rows vượt threshold 180 ngày.

Kết luận:

- Dữ liệu xấu làm retrieval hit rate giảm từ `1.0` xuống `0.625`.
- Token F1 giảm từ `1.0` xuống khoảng `0.684`.
- Judge accuracy giảm từ `1.0` xuống `0.625`.
- Sau repair từ raw snapshot, metrics phục hồi về baseline.

Điều này chứng minh đúng mục tiêu lab: data quality ảnh hưởng rõ ràng đến RAG agent performance.

### Bước 15. Tự review trước khi nộp

Checklist:

| Tiêu chí | Trạng thái |
| --- | --- |
| Code chia module rõ ràng | Đạt |
| Raw/clean/eval/results lưu đầy đủ | Đạt |
| Agent/QA chạy được | Đạt |
| Metrics hợp lý | Đạt |
| Markdown report đọc được | Đạt |
| Chứng minh impact của corruption | Đạt |
| Không hardcode API key | Đạt |
| Có `.env.example` | Đạt |

## 4. Giải thích chi tiết từng file chính

### `src/core/config.py`

File này là trung tâm cấu hình.

Nó định nghĩa:

- Tất cả đường dẫn artifact trong `data/`.
- Provider LLM và API key tương ứng.
- Embedding model.
- Tên Chroma collection cho baseline, corrupted, repaired.
- Crossref source query và filter.
- `freshness_threshold_days = 180`.
- Cờ `REFRESH_SOURCE` và `REFRESH_TEST_SET`.

Điểm hay của file này là các module khác không tự hardcode path. Chỉ cần gọi `load_settings()` là có toàn bộ config.

### `src/core/utils.py`

File tiện ích chung:

- `write_json`, `read_json`
- `write_csv`
- `write_text`
- `normalize_whitespace`
- `safe_slug`
- `first_sentence`
- `now_utc`

Các helper này giúp code gọn hơn và tránh lặp logic đọc/ghi file.

### `src/ingestion/crossref.py`

Nhiệm vụ:

- Gọi Crossref API.
- Parse response JSON.
- Làm sạch abstract khỏi tag XML/JATS.
- Chuẩn hóa ngày publish/update.
- Tạo `PaperRecord`.
- Lưu raw response và raw records.
- Load lại raw snapshot khi không muốn fetch lại.

Điểm quan trọng:

- Nếu Crossref trả lỗi hoặc network lỗi, code có thể fallback sang raw snapshot cũ nếu file đã tồn tại.
- Không dùng trực tiếp JSON Crossref trong toàn bộ pipeline, mà map về `PaperRecord` để schema ổn định.

### `src/ingestion/cleaning.py`

Nhiệm vụ:

- Biến list `PaperRecord` thành `pandas.DataFrame`.
- Loại record xấu.
- Tính `age_days`.
- Tạo `text_for_embedding`.
- Dedupe theo `paper_id`.
- Sort paper mới nhất trước.

Đây là bước quan trọng nhất của data modeling. Nếu clean không tốt thì embedding và evaluation phía sau sẽ bị ảnh hưởng.

### `src/ingestion/corruption.py`

Nhiệm vụ:

- Tạo dataset lỗi từ clean dataset.
- Ghi log corruption.
- Rebuild `text_for_embedding` sau khi làm hỏng dữ liệu.

Corruption được thiết kế để làm hỏng cả content, metadata và freshness. Nhờ vậy quality checks và metrics đều có thay đổi rõ ràng.

### `src/retrieval/embeddings.py`

Nhiệm vụ:

- Load `sentence-transformers/all-MiniLM-L6-v2`.
- Embed documents và query.
- Nếu model không có cache hoặc không tải được, fallback sang hash embedding.

Kiến thức chính:

- Embedding biến text thành vector số.
- Vector gần nhau nghĩa là nội dung có liên quan về mặt ngữ nghĩa.
- ChromaDB dùng vector để tìm top-k document giống query nhất.

### `src/retrieval/index.py`

Nhiệm vụ:

- Build ChromaDB collection.
- Add documents, embeddings, metadata.
- Lưu manifest embedding.
- Load index từ manifest.
- Search top-k.
- Lookup exact theo `paper_id` hoặc `title`.

Điểm quan trọng:

- `documents_by_paper_id` và `documents_by_title` giúp exact lookup nhanh.
- `search()` trả về `SearchResult` gồm paper id, title, score, content và metadata.

### `src/retrieval/llm.py`

Nhiệm vụ:

- Tạo LLM object theo provider đã chọn.
- Kiểm tra API key tương ứng.
- Support Gemini, OpenAI, Anthropic, OpenRouter, Ollama và custom endpoint.

Không hardcode key. Key được đọc từ `.env`.

### `src/retrieval/agent.py`

Nhiệm vụ:

- Tạo agent có hai tool:
  - `semantic_search_papers`
  - `lookup_paper`
- Agent dùng tool để trả lời câu hỏi trên corpus đã index.

Đây là phiên bản agent dùng LangChain tool calling.

### `src/retrieval/qa.py`

Nhiệm vụ:

- Trả lời câu hỏi factual bằng retrieval result.
- Ưu tiên exact title lookup nếu question có title trong dấu nháy.
- Nếu không có exact match thì dùng semantic search.
- Extract answer theo loại câu hỏi.

File này giúp evaluation chạy ổn định ngay cả khi không có API key LLM.

### `src/evaluation/testset.py`

Nhiệm vụ:

- Tạo test set từ cleaned dataframe.
- Lưu vào `data/eval/test_set.json`.
- Bảo đảm mỗi câu có ground truth và document id đúng.

Test set phải deterministic để baseline, corrupted và repaired cùng dùng một bộ câu hỏi.

### `src/evaluation/metrics.py`

Nhiệm vụ:

- Đọc test set.
- Gọi `answer_question`.
- Tính retrieval hit.
- Tính token F1.
- Judge answer bằng LLM nếu có, fallback heuristic nếu không.
- Có optional RAGAS nếu set `RUN_RAGAS=1`.
- Lưu metrics và answers.

Đây là file cho biết agent tốt hay kém sau từng trạng thái dữ liệu.

### `src/observability/quality.py`

Nhiệm vụ:

- Chạy data quality checks.
- Tạo freshness report.
- Lưu JSON report.

Quality checks giúp phát hiện lỗi dữ liệu trước khi lỗi đó làm giảm chất lượng RAG.

### `src/observability/reporting.py`

Nhiệm vụ:

- Sinh `phase1_report.md`.
- Sinh `corruption_report.md`.

Report giúp người đọc không cần mở nhiều file JSON vẫn hiểu pipeline chạy ra sao và metrics thay đổi thế nào.

### `src/pipelines/phase1.py`

Nhiệm vụ:

- Ghép toàn bộ baseline flow.
- Tạo đủ artifact cho raw, clean, embedding, eval, results, quality và report.

Đây là script chính để chạy pha dữ liệu sạch.

### `src/pipelines/corruption_flow.py`

Nhiệm vụ:

- Ghép corruption flow.
- Tự chạy baseline nếu thiếu artifact cần thiết.
- Tạo corrupted dataset.
- Evaluate corrupted.
- Repair từ raw records.
- Evaluate repaired.
- Sinh comparison report.

Đây là script chính để chứng minh impact của data corruption.

## 5. Kiến thức chính của lab

### ETL pipeline

ETL gồm:

1. Extract: lấy dữ liệu từ Crossref.
2. Transform: parse, clean, normalize, tạo schema chuẩn.
3. Load: lưu artifact và nạp vào ChromaDB.

Trong lab này, ETL không chỉ để có data, mà còn để bảo đảm data đủ sạch cho RAG.

### Data modeling

Data modeling là việc quyết định schema dùng trong hệ thống.

Schema tốt cần:

- Có ID ổn định.
- Có title/summary đủ rõ.
- Có metadata cần thiết.
- Có field phục vụ embedding.
- Có field phục vụ observability.

Ở lab này, `PaperRecord` là schema raw đã chuẩn hóa, còn cleaned dataframe là schema phục vụ RAG.

### Embedding

Embedding biến text thành vector số. Các text có nghĩa gần nhau sẽ có vector gần nhau.

Trong RAG:

- Document được embed trước và lưu vào vector store.
- Query của user cũng được embed.
- Vector store tìm top-k document gần query nhất.

### ChromaDB

ChromaDB là vector database. Nó lưu:

- Vector embedding.
- Document text.
- Metadata.
- ID.

Khi query, ChromaDB trả về các document có vector gần query nhất.

### RAG

RAG là Retrieval Augmented Generation.

Ý tưởng:

1. Retrieve context liên quan từ corpus.
2. Dùng context đó để trả lời.

Trong lab này, retrieval được đánh giá bằng `retrieval_hit_rate`, còn answer quality được đánh giá bằng token F1 và judge score.

### Evaluation

Evaluation cần:

- Test set có câu hỏi.
- Ground truth answer.
- Ground truth document ID.
- Hệ thống trả lời.
- Metrics để so sánh.

Nếu không có test set cố định thì rất khó biết thay đổi code/data có làm hệ thống tốt hơn hay tệ hơn.

### Data observability

Data observability là khả năng theo dõi sức khỏe dữ liệu.

Trong lab này gồm:

- Row count.
- Null check.
- Unique check.
- Blank title check.
- Summary length check.
- Freshness check.

Observability giúp phát hiện lỗi dữ liệu trước khi user thấy câu trả lời sai.

### Freshness

Freshness đo dữ liệu có mới không.

Ở lab này:

```text
freshness_threshold_days = 180
```

Nếu `age_days > 180`, record bị xem là stale.

### Corruption testing

Corruption testing là cố ý làm dữ liệu xấu đi để xem hệ thống chịu ảnh hưởng thế nào.

Lab dùng corruption để chứng minh:

- Dữ liệu mất hoặc rỗng làm retrieval/answer giảm.
- Dữ liệu nhiễu làm embedding search yếu hơn.
- Dữ liệu stale làm freshness fail.
- Duplicate làm quality fail.
- Repair đúng từ raw source giúp phục hồi metrics.

### Repair

Repair trong lab không phải sửa từng row corrupted bằng tay. Cách đúng hơn là rebuild cleaned dataset từ raw snapshot gốc.

Lý do:

- Raw source là nguồn đáng tin hơn corrupted clean dataset.
- Rebuild giúp tái áp dụng toàn bộ logic cleaning.
- Artifact repaired nhất quán với baseline.

## 6. Lệnh chạy và kiểm tra

Cài dependency:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv sync
```

Chạy baseline:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv run python script/run_phase1.py
```

Chạy corruption flow:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv run python script/run_corruption_flow.py
```

Kiểm tra cú pháp:

```powershell
$env:UV_CACHE_DIR='E:\AI20K-lab\2A202600675-NguyenBaThanh-Day10\.uv-cache'
uv run python -m compileall src script
```

Nếu muốn fetch lại Crossref:

```powershell
$env:REFRESH_SOURCE='1'
uv run python script/run_phase1.py
```

Nếu muốn tạo lại test set:

```powershell
$env:REFRESH_TEST_SET='1'
uv run python script/run_phase1.py
```

Nếu muốn bật RAGAS:

```powershell
$env:RUN_RAGAS='1'
uv run python script/run_phase1.py
```

Lưu ý: RAGAS có thể chậm hơn và có thể cần cấu hình LLM/API key đầy đủ.

## 7. Liên hệ với rubric

| Rubric | Bài làm đáp ứng bằng gì |
| --- | --- |
| Code structure | Chia module theo `core`, `ingestion`, `retrieval`, `evaluation`, `observability`, `pipelines`. |
| Raw ingestion | Fetch Crossref, parse payload, lưu raw response và raw records. |
| Cleaning/data modeling | Clean schema rõ ràng, có `text_for_embedding`, `age_days`, helper fields. |
| Embedding/vector store | Dùng MiniLM và ChromaDB, có manifest và top-k search. |
| Agent/LLM | Có provider abstraction và QA/agent flow. |
| Evaluation | Có test set, answers, metrics baseline/corrupted/repaired. |
| Data observability | Có quality checks, freshness report, Markdown report. |
| Corruption/comparison | Có corruption log, corrupted metrics, repaired metrics, comparison report. |

## 8. Kết luận ngắn

Lab này cho thấy RAG không chỉ phụ thuộc vào LLM. Dữ liệu đầu vào, quy trình cleaning, index, quality checks và freshness monitoring đều ảnh hưởng trực tiếp đến chất lượng câu trả lời.

Khi dữ liệu sạch, baseline đạt metrics tốt. Khi dữ liệu bị corrupt, retrieval và answer quality giảm. Khi repair bằng cách rebuild từ raw source, metrics phục hồi. Đây là vòng đời quan trọng của một hệ thống RAG có data observability.
