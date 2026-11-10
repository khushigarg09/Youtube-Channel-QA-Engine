# 🎥 YouTube Channel QA Engine

> A YouTube Channel QA Engine that indexes video transcripts and answers cross-video questions with timestamped citations using Hybrid RAG (pgvector + BM25).

## Overview

YouTube Channel QA Engine is a Retrieval-Augmented Generation (RAG) application. It ingests video transcripts from designated YouTube channels, stores relational metadata and chunk embeddings in **PostgreSQL with `pgvector`** (with SQLite fallback for local test suites), manages database schema migrations with **Alembic**, and leverages **BM25 lexical search** combined with **True Reciprocal Rank Fusion (RRF)** to answer natural language questions with timestamped video citations using **Groq (GPT OSS 120B)**.

---

## Architecture

The system unifies relational metadata and vector embeddings into PostgreSQL with `pgvector`:

```text
React + Vite (Frontend)
       │
   FastAPI (Backend)
  ┌────┴───────────────────────────┬───────────────────────────┐
  │                                │                           │
PostgreSQL + pgvector            Alembic                     Groq
- Channels                      - Schema Migrations           - Streaming Answer
- Videos                        - Initial HNSW Vector           Generation
- Transcripts + Embeddings        Index Revisions             - Timestamp Citations
- Dynamic Topics
- Indexing Status
  │                                │
  └────────── BM25 Okapi ──────────┘
                   │
         True RRF Hybrid Fusion
                   │
          Top Transcript Chunks
```

### Retrieval & Ingestion Workflow

1. **Ingestion & Bounded Scope**: Channel metadata and videos are fetched from the uploads playlist with selectable bounded scope (`latest_20`, `latest_50`, or `entire_channel`).
2. **Transcript Processing & Whisper Fallback**: Video subtitles are extracted using `youtube-transcript-api`. If subtitles are unavailable, an optional Groq Whisper audio fallback is attempted with immediate cleanup of temporary `.m4a` files.
3. **Storage & Reindexing Consistency**:
   - Transcripts, channel metadata, dynamic keyphrase topics, and dense vector embeddings (`vector(384)`) are stored atomically in PostgreSQL.
   - Vector search is indexed with HNSW (`vector_cosine_ops`).
   - Re-indexing automatically updates vectors and chunk records with cascading consistency.
4. **Hybrid Retrieval with True RRF**:
   - Semantic similarity search (via pgvector cosine distance `<=>`)
   - Exact keyword matching (BM25Okapi over transcript chunks)
   - Fused using Reciprocal Rank Fusion:
     $$\text{RRF}(d) = \sum \frac{1}{k + \text{rank}}$$
5. **Answer Synthesis & Citation Validation**: Groq streams answers citing timestamps (`https://youtube.com/watch?v={id}&t={seconds}`). Inline citations are verified against retrieved sources.

---

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy 2.0, Alembic, Uvicorn, SlowAPI
- **Relational & Vector Storage**: PostgreSQL 16 + `pgvector` (`pgvector/pgvector:pg16`), with SQLite/Chroma fallback for local development
- **Lexical Search**: `rank-bm25` (BM25Okapi)
- **Embeddings**: `BAAI/bge-small-en-v1.5` (via Hugging Face / Sentence-Transformers)
- **LLM Synthesis**: Groq API (`openai/gpt-oss-120b`)
- **Transcript Extraction**: `youtube-transcript-api`, `yt-dlp`
- **Frontend**: React, Vite, Tailwind CSS, Axios, Lucide Icons
- **Testing & Tooling**: Pytest, Pytest-Mock, HTTPX, Docker Compose

---

## Project Structure

```text
Youtube-Channel-QA-Engine/
├── docker-compose.yml   # PostgreSQL + pgvector container definition
├── backend/
│   ├── alembic/          # Alembic migrations (001_initial_schema_with_pgvector.py)
│   ├── alembic.ini       # Alembic configuration
│   ├── app/
│   │   ├── api/          # FastAPI routers, endpoints, and Pydantic schemas
│   │   ├── database/     # PostgreSQL/SQLite engine, models, and connection lifecycle
│   │   ├── ingest/       # YouTube client, transcript chunker, and pipeline
│   │   ├── rag/          # True RRF hybrid search, pgvector store, Groq synthesis
│   │   ├── scripts/      # init_db.py, evaluate_retrieval.py
│   │   └── services/     # Channel management, indexing orchestration, topic extractor
│   ├── evaluation/       # Benchmark questions (Hussein Nasser backend engineering dataset)
│   ├── tests/            # 35 automated unit and integration tests (zero external API calls)
│   ├── requirements.txt  # Core dependencies (psycopg2-binary, pgvector, alembic)
│   ├── requirements-dev.txt # Test dependencies
│   └── .env.example      # Sample local configuration
└── frontend/
    ├── src/
    │   ├── components/   # ChannelIndexer, ChatWindow, TopicGrid, VideoCard
    │   ├── services/     # Axios client and EventSource streaming handlers
    │   └── App.jsx       # Workspace layout and channel state
    └── package.json
```

---

## Local Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- Docker (optional, for running PostgreSQL + pgvector locally)

### 1. Start PostgreSQL with pgvector (Recommended)

Using the provided `docker-compose.yml`:

```bash
docker compose up -d db
```

This launches PostgreSQL 16 with the `pgvector` extension pre-installed on `localhost:5432`.

### 2. Backend Setup

```bash
cd backend

# Create and activate virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 3. Environment Configuration

Copy `.env.example` to `.env` in the `backend/` directory:

```bash
cp .env.example .env
```

Configure your environment variables:

```env
YOUTUBE_API_KEY=your_youtube_api_v3_key
GROQ_API_KEY=your_groq_api_key

# PostgreSQL with pgvector
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/youtube_qa
VECTOR_STORE=pgvector

GROQ_MODEL=openai/gpt-oss-120b
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

*(Note: If running without Docker/PostgreSQL in lightweight offline mode, `DATABASE_URL=sqlite:///./youtube_knowledge_graph.db` with `VECTOR_STORE=chroma` remains fully supported).*

### 4. Run Schema Migrations (Alembic)

Apply database migrations:

```bash
cd backend
alembic upgrade head
```

Alternatively, initialize tables directly:

```bash
python -m app.scripts.init_db
```

### 5. Run the Backend API

Start the FastAPI development server:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

The API will be available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### 6. Frontend Setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Running Automated Tests

The test suite runs completely offline with zero external API calls:

```bash
cd backend
pytest -v
```

The suite includes 35 tests covering:
- **`test_transcripter.py`**: Chunking boundary conditions, timestamp preservation, overlap validation, duplicate suppression, temporary audio cleanup, and specific transcript-access fallback exceptions.
- **`test_topic_extractor.py`**: Unsupervised keyphrase discovery, candidate normalization, and timestamp mapping.
- **`test_retrieval.py`**: BM25 keyword matching, vector integration, cross-channel isolation, True RRF mathematical ordering, and vector cleanup safe failure paths.
- **`test_api.py`**: Input validation (URL format, message length bounds), 404 handling, 409 conflict on concurrent indexing, and client error masking.
- **`test_rag_generation.py`**: Context scoping, citation instructions, metadata streaming, and empty retrieval handling.

---

## Retrieval Evaluation

A retrieval evaluation benchmark is included using questions from Hussein Nasser's backend engineering channel:

```bash
cd backend
python -m app.scripts.evaluate_retrieval
```

To display retrieved context passages for manual inspection:

```bash
python -m app.scripts.evaluate_retrieval --show-results
```

Calculated metrics:
- **Recall@5**: Fraction of queries where the ground-truth video appears in the top 5 results.
- **Recall@10**: Fraction of queries where the ground-truth video appears in the top 10 results.
- **Mean Reciprocal Rank (MRR)**: Average reciprocal rank of the first relevant chunk.
- **Average Retrieval Latency**: Mean end-to-end hybrid retrieval duration in milliseconds.

---

## Limitations

- **In-Process Background Tasks**: FastAPI background tasks run in-process and are not durable distributed job queues. Process termination will stop in-progress jobs (automatically self-healed to `idle` on startup).
- **Transcript Availability**: Retrieval and answer quality depend directly on YouTube transcript availability (manual or auto-generated captions).
- **Citations & Verification**: Generated answers should be checked using timestamp citations. While citations are verified against retrieved chunks, LLM outputs must be confirmed by reviewing source footage.
