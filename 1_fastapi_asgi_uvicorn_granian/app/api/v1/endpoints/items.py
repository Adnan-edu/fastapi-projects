from typing import Optional

from fastapi import APIRouter, HTTPException, Path
from pydantic import BaseModel, Field

from app.services import items as items_service

router = APIRouter(prefix="/items", tags=["items"])


class ItemCreate(BaseModel):
    model_config = {"extra": "forbid"}

    name: str = Field(min_length=1)
    description: Optional[str] = None


class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None


@router.get("", response_model=list[ItemResponse])
def list_items():
    return items_service.list_items()


@router.post("", response_model=ItemResponse, status_code=201)
def create_item(body: ItemCreate):
    item = items_service.create_item(name=body.name, description=body.description)
    return item


@router.get("/{item_id}", response_model=ItemResponse)
def get_item(item_id: int = Path(gt=0)):
    item = items_service.get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return item