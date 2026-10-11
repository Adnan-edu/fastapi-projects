from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app.core.casbin_enforcer import require_permission
from app.core.auth import User
from app.services import document_service

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class DocumentUpdate(BaseModel):
    title: str | None = None
    content: str | None = None


class DocumentResponse(BaseModel):
    id: int
    title: str
    content: str
    owner: str


@router.get("/", response_model=list[DocumentResponse])
async def list_documents(user: User = Depends(require_permission("document", "read"))):
    return document_service.list_documents()


@router.get("/{doc_id}", response_model=DocumentResponse)
async def get_document(
    doc_id: int,
    user: User = Depends(require_permission("document", "read")),
):
    doc = document_service.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    return doc


@router.post("/", response_model=DocumentResponse, status_code=status.HTTP_201_CREATED)
async def create_document(
    body: DocumentCreate,
    user: User = Depends(require_permission("document", "create")),
):
    doc = document_service.create_document(body.title, body.content, owner=user.username)
    return doc


@router.put("/{doc_id}", response_model=DocumentResponse)
async def update_document(
    doc_id: int,
    body: DocumentUpdate,
    user: User = Depends(require_permission("document", "update")),
):
    if not body.title and not body.content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="At least one of 'title' or 'content' must be provided",
        )
    doc = document_service.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.owner != user.username and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own documents",
        )
    updated = document_service.update_document(doc_id, body.title, body.content)
    return updated


@router.delete("/{doc_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    doc_id: int,
    user: User = Depends(require_permission("document", "delete")),
):
    doc = document_service.get_document(doc_id)
    if doc is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found")
    if doc.owner != user.username and user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own documents",
        )
    document_service.delete_document(doc_id)