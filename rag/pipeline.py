"""
RAG (Retrieval-Augmented Generation) layer.

Architecture:
  - ChromaDB: local vector store for scraped documents
  - Sentence Transformers: local embeddings (no API cost)
  - Groq LLM (llama3-70b): fast inference for query answering
  - LangChain: orchestration

Flow:
  1. Scraped documents (filings, news, SERP) → chunked → embedded → ChromaDB
  2. User query → embed → similarity search → top-k chunks
  3. Chunks + live market data → Groq → structured answer

Supports queries like:
  "What regulatory changes in Singapore affect our crypto ops this week?"
  "Which exchange has the best BTC spread right now?"
  "Are there any unusual arbitrage signals between Binance and OKX?"
"""
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Optional imports — RAG works in degraded mode if missing
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False
    logger.warning("ChromaDB not available — RAG will use live data only")

try:
    from langchain_groq import ChatGroq
    from langchain.schema import HumanMessage, SystemMessage
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False
    logger.warning("LangChain/Groq not available — AI queries disabled")

from data.store import store
from config.settings import settings


class RAGPipeline:
    def __init__(self):
        self._chroma_client = None
        self._collection = None
        self._llm = None
        self._embed_fn = None
        self._initialized = False

    def initialize(self):
        """Lazy init — called once on first use."""
        if self._initialized:
            return

        # ChromaDB
        if CHROMA_AVAILABLE:
            try:
                self._chroma_client = chromadb.PersistentClient(path="data/vectors")
                self._embed_fn = embedding_functions.DefaultEmbeddingFunction()
                self._collection = self._chroma_client.get_or_create_collection(
                    name="marketpulse_docs",
                    embedding_function=self._embed_fn,
                    metadata={"hnsw:space": "cosine"}
                )
                logger.info("ChromaDB initialized")
            except Exception as e:
                logger.warning(f"ChromaDB init failed: {e}")

        # Groq LLM
        if GROQ_AVAILABLE and settings.GROQ_API_KEY:
            try:
                self._llm = ChatGroq(
                    api_key=settings.GROQ_API_KEY,
                    model=settings.GROQ_MODEL,
                    temperature=0.1,
                    max_tokens=1024,
                )
                logger.info(f"Groq LLM initialized: {settings.GROQ_MODEL}")
            except Exception as e:
                logger.warning(f"Groq init failed: {e}")

        self._initialized = True

    def ingest_documents(self, docs: list[dict]):
        """Chunk and embed new scraped documents into ChromaDB."""
        if not self._collection or not docs:
            return 0
        try:
            ids, texts, metadatas = [], [], []
            for doc in docs:
                doc_id = f"{doc['type']}_{hash(doc['content'])}_{datetime.utcnow().timestamp()}"
                ids.append(doc_id)
                texts.append(doc["content"][:2000])  # max chunk size
                metadatas.append({
                    "type": doc["type"],
                    "source": doc["source"],
                    "url": doc.get("url", ""),
                    "ts": doc.get("ts", ""),
                })
            self._collection.upsert(ids=ids, documents=texts, metadatas=metadatas)
            logger.info(f"RAG: ingested {len(docs)} documents")
            return len(docs)
        except Exception as e:
            logger.warning(f"RAG ingest error: {e}")
            return 0

    def _retrieve_context(self, query: str, n_results: int = 5) -> str:
        """Retrieve top-k relevant chunks from ChromaDB."""
        if not self._collection:
            return ""
        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=min(n_results, self._collection.count() or 1),
                include=["documents", "metadatas"]
            )
            chunks = results.get("documents", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            context_parts = []
            for chunk, meta in zip(chunks, metas):
                context_parts.append(
                    f"[{meta.get('type','').upper()} | {meta.get('source','')} | {meta.get('ts','')}]\n{chunk}"
                )
            return "\n\n---\n\n".join(context_parts)
        except Exception as e:
            logger.warning(f"RAG retrieval error: {e}")
            return ""

    def _build_live_context(self) -> str:
        """Build a compact live market snapshot for the LLM prompt."""
        snap = store.snapshot()
        lines = ["=== LIVE MARKET DATA ==="]

        # Best spreads
        prices = snap.get("exchange_prices", {})
        if prices:
            lines.append("\nBTC/USDT spreads (live):")
            for ex, syms in sorted(prices.items()):
                btc = syms.get("BTC/USDT", {})
                if btc:
                    lines.append(
                        f"  {ex}: bid=${btc.get('bid',0):,.2f} "
                        f"ask=${btc.get('ask',0):,.2f} "
                        f"spread={btc.get('spread_pct',0):.3f}%"
                    )

        # Recent anomalies
        anomalies = snap.get("anomalies", [])[:5]
        if anomalies:
            lines.append("\nActive anomalies:")
            for a in anomalies:
                lines.append(f"  [{a['severity'].upper()}] {a['description']}")

        # Sentiment
        sentiment = snap.get("sentiment", {})
        if sentiment:
            lines.append("\nSentiment:")
            for key, s in sentiment.items():
                lines.append(f"  {key}: {s.get('score',50):.1f}% bullish ({s.get('mentions',0)} mentions)")

        # Recent filings
        filings = snap.get("regulatory_filings", [])[:3]
        if filings:
            lines.append("\nRecent regulatory filings:")
            for f in filings:
                lines.append(f"  [{f['source']}] {f['title']}")

        return "\n".join(lines)

    async def query(self, question: str) -> dict:
        """Answer a natural language question using RAG + live data."""
        self.initialize()

        if not self._llm:
            return {
                "answer": "AI query layer not configured. Set GROQ_API_KEY in .env",
                "sources": [],
                "model": "unavailable"
            }

        # Retrieve relevant docs from vector store
        doc_context = self._retrieve_context(question, n_results=5)
        live_context = self._build_live_context()

        system_prompt = """You are MarketPulse Intelligence — an enterprise crypto market analyst AI.
You have access to:
1. Real-time exchange pricing and spread data across 10 exchanges
2. Regulatory filings from SEC, MAS (Singapore), and OJK (Indonesia)
3. Sentiment data from Reddit and X (Twitter)
4. Job posting signals from major crypto companies
5. News from 20+ sources

Rules:
- Be concise, precise, and actionable
- Cite sources when available (exchange name, regulator, filing date)
- Flag confidence level if uncertain
- For regulatory questions: note jurisdiction and effective dates
- For spread/pricing: give specific exchange names and numbers
- Never hallucinate — if data is unavailable, say so clearly"""

        user_prompt = f"""QUESTION: {question}

{live_context}

RELEVANT DOCUMENT CONTEXT:
{doc_context if doc_context else "(No archived documents matched — answering from live data only)"}

Provide a clear, actionable answer for an enterprise crypto operations team."""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            response = await self._llm.ainvoke(messages)
            answer = response.content

            # Extract sources from metadata
            sources = []
            if self._collection:
                results = self._collection.query(
                    query_texts=[question], n_results=3,
                    include=["metadatas"]
                )
                for meta in results.get("metadatas", [[]])[0]:
                    if meta.get("url"):
                        sources.append({
                            "type": meta.get("type"),
                            "source": meta.get("source"),
                            "url": meta.get("url"),
                        })

            return {
                "answer": answer,
                "sources": sources,
                "model": settings.GROQ_MODEL,
                "ts": datetime.utcnow().isoformat()
            }
        except Exception as e:
            logger.error(f"RAG query error: {e}")
            return {
                "answer": f"Query failed: {str(e)}",
                "sources": [],
                "model": settings.GROQ_MODEL
            }

    def flush_rag_buffer(self):
        """Drain the store's RAG buffer and ingest into ChromaDB."""
        self.initialize()
        docs = store.drain_rag_buffer()
        if docs:
            return self.ingest_documents(docs)
        return 0


# Global singleton
rag = RAGPipeline()
