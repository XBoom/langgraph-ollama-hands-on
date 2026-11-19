"""Agentic RAG 单测（词法向量，不需要 Ollama）。"""

from __future__ import annotations

from agent.rag import (
    LexicalBagEmbedding,
    build_vectorstore,
    ensure_rag_registered,
    load_corpus,
    make_retrieve_tool,
)
from agent.tools import get_tools


def test_load_corpus_has_policy_chunks():
    docs = load_corpus()
    sources = {d.metadata["source"] for d in docs}
    assert {"refund.md", "shipping.md", "warranty.md"} <= sources
    assert any("退款" in d.page_content for d in docs)


def test_lexical_retrieve_hits_refund():
    tool = make_retrieve_tool(embeddings="lexical", k=3)
    text = tool.invoke({"query": "无理由退款运费谁承担"})
    assert "refund" in text.lower() or "退款" in text or "运费" in text
    assert "[" in text  # chunk_id 前缀


def test_vectorstore_similarity_prefers_related_chunk():
    emb = LexicalBagEmbedding()
    store = build_vectorstore(emb)
    hits = store.similarity_search("质保多久电子产品", k=2)
    blob = " ".join(h.page_content for h in hits)
    assert "质保" in blob or "warranty" in hits[0].metadata.get("source", "")


def test_ensure_rag_registered_in_get_tools():
    ensure_rag_registered(embeddings="lexical", force=True)
    names = {t.name for t in get_tools()}
    assert "retrieve_policy" in names
    assert "calculator" in names
