"""Agentic RAG：语料 → 切块 → 向量库 → 检索 Tool → 进 create_agent。

默认用词法向量（无外网/无 Ollama），单测与 demo 默认可跑。
真语义检索：ensure_rag_registered(embeddings=\"ollama\")，需本机
`ollama pull nomic-embed-text`。

复用：[src: langchain InMemoryVectorStore + create_retriever_tool]
"""

from __future__ import annotations

import hashlib
import math
import re
from pathlib import Path
from typing import Literal, Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.prompts import PromptTemplate
from langchain_core.tools import BaseTool
from langchain_core.tools.retriever import create_retriever_tool
from langchain_core.vectorstores import InMemoryVectorStore

from agent.tools import get_tools, register_tool

RAG_DATA_DIR = Path(__file__).resolve().parent / "rag_data"
DEFAULT_EMBED_MODEL = "nomic-embed-text"
_RETRIEVE_NAME = "retrieve_policy"

_registered_fingerprint: str | None = None


class LexicalBagEmbedding(Embeddings):
    """离线词法向量：字符 bigram 哈希到固定维，便于无 Ollama 时做相似检索。

    不是生产级 embedding；只为 hands-on / 单测提供可复现的向量空间。
    """

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        norm = text.casefold()
        if len(norm) < 2:
            norm = norm + " "
        for i in range(len(norm) - 1):
            gram = norm[i : i + 2]
            h = int(hashlib.md5(gram.encode("utf-8")).hexdigest(), 16)
            vec[h % self.dim] += 1.0
        norm_l2 = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm_l2 for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def load_corpus(data_dir: Path | None = None) -> list[Document]:
    """读取 rag_data 下 markdown，按空行切块，metadata 带 source / chunk_id。"""
    root = data_dir or RAG_DATA_DIR
    docs: list[Document] = []
    for path in sorted(root.glob("*.md")):
        text = path.read_text(encoding="utf-8").strip()
        chunks = [c.strip() for c in re.split(r"\n\s*\n", text) if c.strip()]
        for i, chunk in enumerate(chunks):
            docs.append(
                Document(
                    page_content=chunk,
                    metadata={"source": path.name, "chunk_id": f"{path.stem}-{i}"},
                )
            )
    if not docs:
        raise FileNotFoundError(f"no markdown corpus under {root}")
    return docs


def build_vectorstore(
    embeddings: Embeddings,
    documents: Sequence[Document] | None = None,
) -> InMemoryVectorStore:
    docs = list(documents) if documents is not None else load_corpus()
    return InMemoryVectorStore.from_documents(docs, embedding=embeddings)


def _resolve_embeddings(
    embeddings: Embeddings | Literal["lexical", "ollama"],
) -> Embeddings:
    if isinstance(embeddings, Embeddings):
        return embeddings
    if embeddings == "lexical":
        return LexicalBagEmbedding()
    if embeddings == "ollama":
        from langchain_ollama import OllamaEmbeddings

        return OllamaEmbeddings(
            model=DEFAULT_EMBED_MODEL,
            base_url="http://127.0.0.1:11434",
        )
    raise ValueError(f"unknown embeddings: {embeddings!r}")


def make_retrieve_tool(
    *,
    embeddings: Embeddings | Literal["lexical", "ollama"] = "lexical",
    k: int = 3,
    documents: Sequence[Document] | None = None,
) -> BaseTool:
    """构造检索工具（不自动注册）。返回带 [chunk_id] 前缀的片段文本。"""
    emb = _resolve_embeddings(embeddings)
    store = build_vectorstore(emb, documents=documents)
    retriever = store.as_retriever(search_kwargs={"k": k})
    return create_retriever_tool(
        retriever,
        name=_RETRIEVE_NAME,
        description=(
            "从内部政策知识库检索相关段落（退款/配送/质保）。"
            "回答政策类问题前应调用；传入自然语言查询。"
        ),
        document_prompt=PromptTemplate.from_template(
            "[{chunk_id} | {source}] {page_content}"
        ),
        document_separator="\n\n---\n\n",
    )


def ensure_rag_registered(
    *,
    embeddings: Embeddings | Literal["lexical", "ollama"] = "lexical",
    k: int = 3,
    force: bool = False,
) -> BaseTool:
    """注册 retrieve_policy 到本地工具仓；同配置幂等，force=True 可换 embedding。"""
    global _registered_fingerprint
    emb = _resolve_embeddings(embeddings)
    fp = f"{type(emb).__name__}:{k}"
    existing = next((t for t in get_tools() if t.name == _RETRIEVE_NAME), None)
    if not force and _registered_fingerprint == fp and existing is not None:
        return existing

    tool = make_retrieve_tool(embeddings=emb, k=k)
    register_tool(tool)
    _registered_fingerprint = fp
    return tool


def format_hits_for_prompt(docs: Sequence[Document]) -> str:
    """测试/调试：把 Document 列表格式化成带 chunk_id 的文本。"""
    parts: list[str] = []
    for d in docs:
        cid = d.metadata.get("chunk_id", "?")
        parts.append(f"[{cid}] {d.page_content}")
    return "\n\n".join(parts)


# import 本模块即注册默认（词法）检索工具，与 calculator 一样进 get_tools()
ensure_rag_registered(embeddings="lexical")
