"""In-memory KnowledgeStore for unit tests: token-overlap scoring, no vectors, no network.

Records every (query, filter) it receives so tests can assert what a retriever issued.
"""

import re
from dataclasses import replace

from backend.db.knowledge_store import Document, KnowledgeStore, SearchFilter

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class InMemoryKnowledgeStore(KnowledgeStore):
    def __init__(self, documents: list[Document] | None = None) -> None:
        self.documents: list[Document] = list(documents or [])
        self.calls: list[tuple[str, SearchFilter | None]] = []

    def _matches(self, doc: Document, filter: SearchFilter | None) -> bool:
        if filter is None or filter.is_empty:
            return True
        if filter.has_age and not (
            doc.age_min_months <= filter.age_max_months
            and doc.age_max_months >= filter.age_min_months
        ):
            return False
        return not filter.authorities or doc.authority in filter.authorities

    async def search(
        self, query: str, top_k: int = 5, filter: SearchFilter | None = None
    ) -> list[Document]:
        self.calls.append((query, filter))
        q = _tokens(query)
        if not q:
            return []
        scored = []
        for doc in self.documents:
            if not self._matches(doc, filter):
                continue
            overlap = len(q & _tokens(doc.content)) / len(q)
            if overlap > 0:
                scored.append(replace(doc, score=round(overlap, 4), embedding=None))
        scored.sort(key=lambda d: (-d.score, d.document_id or "", d.chunk_index))
        return scored[:top_k]

    async def upsert(self, documents: list[Document], document_id: str | None = None) -> int:
        ids = {document_id or d.document_id for d in documents}
        self.documents = [d for d in self.documents if d.document_id not in ids]
        for d in documents:
            self.documents.append(replace(d, document_id=document_id or d.document_id))
        return len(documents)

    async def delete(self, document_id: str) -> int:
        before = len(self.documents)
        self.documents = [d for d in self.documents if d.document_id != document_id]
        return before - len(self.documents)

    async def count(self) -> int:
        return len(self.documents)

    async def list_document_hashes(self) -> dict[str, str]:
        return {d.document_id: d.content_hash or "" for d in self.documents if d.document_id}
