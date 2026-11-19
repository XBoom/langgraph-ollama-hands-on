"""Agentic RAG 单测（词法向量，不需要 Ollama）+ 可选 Ollama embedding 集成。"""

from __future__ import annotations

import pytest

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


def test_rag_corpus_mentions_shared_snippet_facts():
    """rag_data 长文须覆盖 policy_snippets 里的关键事实（避免两套真相）。"""
    from agent.policy_snippets import POLICY_BY_TOPIC

    blob = "\n".join(d.page_content for d in load_corpus())
    assert "7 天" in blob and "退款" in blob
    assert "99" in blob and "包邮" in blob
    assert "12 个月" in blob or "12个月" in blob.replace(" ", "")
    assert "refund" in POLICY_BY_TOPIC and "warranty" in POLICY_BY_TOPIC


@pytest.mark.integration
def test_ollama_embedding_retrieve_smoke():
    """需本机 Ollama 且已 pull nomic-embed-text；日常 -m 'not integration' 跳过。"""
    import urllib.request

    try:
        urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"ollama not reachable: {exc}")

    try:
        tool = make_retrieve_tool(embeddings="ollama", k=2)
        text = tool.invoke({"query": "电子产品质保多久"})
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"nomic-embed-text unavailable: {exc}")

    assert "质保" in text or "warranty" in text.lower() or "12" in text
