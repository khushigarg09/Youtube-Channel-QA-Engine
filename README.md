# 🎥 YouTube Channel QA Engine
> **Turn any YouTube channel into an AI-powered QA knowledge base with multi-video synthesis and clickable timestamp citations.**

## Overview
YouTube Channel QA Engine is a full-stack Retrieval-Augmented Generation (RAG) application that ingests entire YouTube channels, processes their transcripts, and allows users to ask natural language questions across the creator's entire video catalog.

## Problem Statement
Standard YouTube search is limited to exact keyword matches against video titles and short descriptions. When researching complex topics across a creator's archive (e.g., *"How has this creator's advice on investing changed over the last 3 years?"*), users are forced to manually scrub through dozens of hours of video footage.

## Solution
This project automates the ingestion of a channel's entire transcript history, chunks the text semantically, and stores it in a hybrid vector/relational database. Users can ask complex queries and receive synthesized, streaming answers from **Llama 3.3**, complete with clickable citations that jump directly to the exact timestamp in the source video.

## Key Features
- **Cross-Video Knowledge Synthesis**: Queries span across dozens of videos simultaneously, not just single clips.
- **Hybrid Retrieval Engine (RRF)**: Blends semantic vector embeddings with exact lexical keyword matching (BM25) via Reciprocal Rank Fusion.
- **Clickable Timestamp Citations**: Answers include deep links (`https://youtu.be/<id>?t=<seconds>`) to verify the source instantly.
- **Dynamic Topic Discovery**: Unsupervised extraction of key concepts (tech, finance, history) without hardcoded dictionaries.
- **Real-Time SSE Streaming**: Live percentage progress for ingestion and token-by-token streaming for LLM answers.
- **Data Export**: Export complete channel transcripts and metadata to JSON or CSV.

## Architecture
The system operates in three main phases: Ingestion, Storage, and RAG Synthesis.

```text
Step 1: INGESTION                   Step 2: STORAGE                  Step 3: CHAT & SEARCH
=================                   ===============                  =====================

[ YouTube Channel URL ]                                             [ User Question ]
       │                                                                   │
       ▼                                                                   ▼
Fetch metadata & transcripts (YouTube API)                           Hybrid Search (RRF)
       │                                                                   │
       ▼                                                                   ▼
Chunk text & overlap                ┌────────────────────────┐      Synthesize answer
       │                            │  ChromaDB (Vectors)    │ ───► Groq (Llama 3.3)
       ├──────────────────────────► │  SQLite/PG (Metadata)  │             │
       │                            └────────────────────────┘             ▼
Extract dynamic topics                                              Answer + Clickable
                                                                    Timestamp Links
```

## Tech Stack
- **Programming Languages**: Python 3.10+, JavaScript (ES6+)
- **Frameworks/Libraries**: FastAPI, React, Tailwind CSS, LangChain, SQLAlchemy
- **AI/ML Models**: Llama 3.3 70B (via Groq), `BAAI/bge-small-en-v1.5` (Local Embeddings)
- **Databases**: ChromaDB (Vector Store), PostgreSQL / SQLite (Relational Store)
- **APIs/Services**: YouTube Data API v3, Groq API
- **Testing/Tools**: Pytest, Vite, Axios, Uvicorn

## Project Structure
```text
YouTube-Knowledge-Graph/
├── backend/
│   ├── app/
│   │   ├── api/          # FastAPI routers and Pydantic schemas
│   │   ├── database/     # SQLAlchemy models and connection pooling
│   │   ├── ingest/       # YouTube API integration and background workers
│   │   ├── rag/          # Hybrid search, LangChain prompts, and LLM integration
│   │   └── services/     # Dynamic topic extraction and business logic
│   ├── tests/            # 18 Pytest unit and integration tests
│   ├── requirements.txt  
│   └── main.py           # Application entrypoint and lifespan hooks
└── frontend/
    ├── src/
    │   ├── components/   # React UI (ChatWindow, ChannelIndexer, TopicGrid)
    │   ├── services/     # Axios API client and EventSource handlers
    │   └── App.jsx       # Main layout and state management
    └── package.json      
```

## Installation

### Prerequisites
- Python 3.10+
- Node.js 18+

### 1. Backend Setup
```bash
cd backend
python -m venv venv
# Windows: .\venv\Scripts\activate | Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
```

### 2. Frontend Setup
```bash
cd frontend
npm install
```

## Environment Variables
Create a `.env` file in the `backend/` directory:

```env
YOUTUBE_API_KEY=<your_youtube_api_v3_key>
GROQ_API_KEY=<your_groq_api_key>
DATABASE_URL=sqlite:///./youtube_knowledge_graph.db
# Or use PostgreSQL: DATABASE_URL=postgresql://user:pass@host/db?sslmode=require
CHROMA_DB_DIR=./chroma_db
GROQ_MODEL=llama-3.3-70b-versatile
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

## Usage
1. **Start Backend**: `python -m uvicorn app.main:app --reload` (Runs on `http://127.0.0.1:8000`)
2. **Start Frontend**: `npm run dev` (Runs on `http://localhost:5173`)
3. **Index a Channel**: Paste a YouTube channel URL into the dashboard. Watch the SSE progress bar.
4. **Chat**: Select the indexed channel and ask a question. Click the generated citations to open the video at the exact timestamp.
