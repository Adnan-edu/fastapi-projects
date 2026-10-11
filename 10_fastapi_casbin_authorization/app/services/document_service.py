from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Document:
    id: int
    title: str
    content: str
    owner: str


_next_id: int = 4
_documents: dict[int, Document] = {
    1: Document(id=1, title="Quarterly Report", content="Q4 revenue exceeded targets.", owner="alice"),
    2: Document(id=2, title="Meeting Notes", content="Decided to migrate to Casbin.", owner="bob"),
    3: Document(id=3, title="Onboarding Guide", content="Welcome new team members.", owner="alice"),
}


def list_documents() -> list[Document]:
    return list(_documents.values())


def get_document(doc_id: int) -> Document | None:
    return _documents.get(doc_id)


def create_document(title: str, content: str, owner: str) -> Document:
    global _next_id
    doc = Document(id=_next_id, title=title, content=content, owner=owner)
    _documents[_next_id] = doc
    _next_id += 1
    return doc


def update_document(doc_id: int, title: str | None, content: str | None) -> Document | None:
    doc = _documents.get(doc_id)
    if doc is None:
        return None
    if title is not None:
        doc.title = title
    if content is not None:
        doc.content = content
    return doc


def delete_document(doc_id: int) -> bool:
    return _documents.pop(doc_id, None) is not None


def _reset_store():
    global _next_id, _documents
    _next_id = 4
    _documents = {
        1: Document(id=1, title="Quarterly Report", content="Q4 revenue exceeded targets.", owner="alice"),
        2: Document(id=2, title="Meeting Notes", content="Decided to migrate to Casbin.", owner="bob"),
        3: Document(id=3, title="Onboarding Guide", content="Welcome new team members.", owner="alice"),
    }