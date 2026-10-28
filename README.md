# 🎥 YouTube Channel QA Engine

> A local YouTube Channel QA Engine that indexes video transcripts and answers cross-video questions with timestamped citations.

## Overview

YouTube Channel QA Engine is a local, single-user Retrieval-Augmented Generation (RAG) application. It ingests video transcripts from designated YouTube channels, stores metadata and transcripts in **SQLite**, indexes chunk embeddings in **ChromaDB**, and leverages **BM25 lexical search** combined with **True Reciprocal Rank Fusion (RRF)** to answer natural language questions with timestamped video citations using **Groq (Llama 3.3)**.

---

## Architecture

The system is designed for simple, local single-user execution without cloud database or container dependencies:

```text
React + Vite (Frontend)
       │
   FastAPI (Backend)
  ┌────┴───────────────────────────┬───────────────────────────┐
  │                                │                           │
SQLite                         ChromaDB                      Groq
- Channels                      - Chunk Embeddings            - Streaming Answer
- Videos                        - Vector Search                 Generation
- Transcripts                   - Local Directory Persistence - Timestamp Citations
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
   - Vectors are stored in local ChromaDB collections.
   - Text chunks, channel metadata, and dynamic keyphrase topics are stored in SQLite.
   - Re-indexing automatically deletes stale vectors and chunk records to maintain consistency.
4. **Hybrid Retrieval with True RRF**:
   - Semantic similarity search (ChromaDB)
   - Exact keyword matching (BM25Okapi over SQLite chunks)
   - Fused using Reciprocal Rank Fusion:
     $$\text{RRF}(d) = \sum \frac{1}{k + \text{rank}}$$
5. **Answer Synthesis & Citation Validation**: Groq streams answers citing timestamps (`https://youtube.com/watch?v={id}&t={seconds}`). Inline citations are verified against retrieved sources.

---

## Tech Stack

- **Backend**: Python 3.10+, FastAPI, SQLAlchemy, Uvicorn, SlowAPI
- **Relational Storage**: SQLite (`youtube_knowledge_graph.db`)
- **Vector Storage**: ChromaDB (`./chroma_db`)
- **Lexical Search**: `rank-bm25` (BM25Okapi)
- **Embeddings**: `BAAI/bge-small-en-v1.5` (via Hugging Face / Sentence-Transformers)
- **LLM Synthesis**: Groq API (`llama-3.3-70b-versatile`)
- **Transcript Extraction**: `youtube-transcript-api`, `yt-dlp`
- **Frontend**: React, Vite, Tailwind CSS, Axios, Lucide Icons
- **Testing**: Pytest, Pytest-Mock, HTTPX

---

## Project Structure

```text
Youtube-Channel-QA-Engine/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers, endpoints, and Pydantic schemas
│   │   ├── database/     # SQLite engine, models, and connection lifecycle
│   │   ├── ingest/       # YouTube client, transcript chunker, and pipeline
│   │   ├── rag/          # True RRF hybrid search, Chroma vector store, Groq synthesis
│   │   ├── scripts/      # init_db.py, evaluate_retrieval.py
│   │   └── services/     # Channel management, indexing orchestration, topic extractor
│   ├── evaluation/       # Benchmark questions (Hussein Nasser backend engineering dataset)
│   ├── tests/            # 35 automated unit and integration tests (zero external API calls)
│   ├── requirements.txt  # Core dependencies
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

### 1. Backend Setup

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

### 2. Environment Configuration

Copy `.env.example` to `.env` in the `backend/` directory:

```bash
cp .env.example .env
```

Set your API keys:

```env
YOUTUBE_API_KEY=your_youtube_api_v3_key
GROQ_API_KEY=your_groq_api_key
DATABASE_URL=sqlite:///./youtube_knowledge_graph.db
CHROMA_DB_DIR=./chroma_db
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

### 3. Initialize SQLite Database (Required First Step)

Database table creation is explicitly decoupled from application lifespan. Initialize database tables before starting the backend server:

```bash
python -m app.scripts.init_db
```

### 4. Run the Backend API

Once tables are created, start the FastAPI development server:

```bash
python -m uvicorn app.main:app --reload --port 8000
```

> **Required Startup Order**:
> 1. `python -m app.scripts.init_db`
> 2. `python -m uvicorn app.main:app --reload --port 8000`

The API will be available at `http://127.0.0.1:8000`. Interactive OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### 5. Frontend Setup

In a separate terminal:

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173` in your browser.

---

## Running Automated Tests

The test suite runs completely offline without making external calls to YouTube, Groq, or third-party services:

```bash
cd backend
pytest -v
```

The suite includes 35 tests covering:
- **`test_transcripter.py`**: Chunking boundary conditions, timestamp preservation, overlap validation, duplicate suppression, temporary audio cleanup, and specific transcript-access fallback exceptions.
- **`test_topic_extractor.py`**: Unsupervised keyphrase discovery, candidate normalization, and timestamp mapping.
- **`test_retrieval.py`**: BM25 keyword matching, Chroma integration, cross-channel isolation, True RRF mathematical ordering, and vector cleanup safe failure paths.
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

- **Local & Single-User**: This application is designed for local, single-user use. SQLite is not intended for distributed multi-user indexing workloads.
- **In-Process Background Tasks**: FastAPI background tasks run in-process and are not durable distributed job queues. Process termination will stop in-progress jobs (automatically self-healed to `idle` on startup).
- **Transcript Availability**: Retrieval and answer quality depend directly on YouTube transcript availability (manual or auto-generated captions).
- **Citations & Verification**: Generated answers should be checked using timestamp citations. While citations are verified against retrieved chunks, LLM outputs must be confirmed by reviewing source footage.
