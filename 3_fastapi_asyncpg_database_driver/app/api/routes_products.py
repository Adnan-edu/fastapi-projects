from fastapi import APIRouter, HTTPException, status

from app.schemas.product import BulkStockUpdate, ProductCreate, ProductListResponse, ProductResponse, ProductUpdate
from app.services import product_service

router = APIRouter(prefix="/api/v1/products", tags=["products"])


@router.post("/", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(product_data: ProductCreate):
    product = await product_service.create_product_service(product_data)
    return product


@router.get("/", response_model=ProductListResponse)
async def list_products():
    result = await product_service.list_products_service()
    return result


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(product_id: int):
    product = await product_service.get_product_service(product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(product_id: int, product_data: ProductUpdate):
    product = await product_service.update_product_service(product_id, product_data)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(product_id: int):
    deleted = await product_service.delete_product_service(product_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")


@router.post("/bulk-stock-update", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_stock_update(data: BulkStockUpdate):
    updates = [(item.product_id, item.stock_quantity) for item in data.items]
    await product_service.bulk_update_stock_service(updates)