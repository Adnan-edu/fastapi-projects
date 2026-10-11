from decimal import Decimal

from app.repositories.product_repository import (
    bulk_update_stock,
    create_product,
    delete_product,
    get_product_by_id,
    list_products,
    update_product,
)
from app.schemas.product import ProductCreate, ProductListResponse, ProductResponse, ProductUpdate


async def create_product_service(product_data: ProductCreate) -> ProductResponse:
    product_dict = await create_product(
        name=product_data.name,
        description=product_data.description,
        price=product_data.price,
        stock_quantity=product_data.stock_quantity,
    )
    return ProductResponse.model_validate(product_dict)


async def get_product_service(product_id: int) -> ProductResponse | None:
    product_dict = await get_product_by_id(product_id)
    if product_dict is None:
        return None
    return ProductResponse.model_validate(product_dict)


async def list_products_service() -> ProductListResponse:
    products_data = await list_products()
    products = [ProductResponse.model_validate(p) for p in products_data]
    return ProductListResponse(products=products, count=len(products))


async def update_product_service(
    product_id: int,
    product_data: ProductUpdate,
) -> ProductResponse | None:
    update_fields = product_data.model_dump(exclude_unset=True)
    if not update_fields:
        product_dict = await get_product_by_id(product_id)
        if product_dict is None:
            return None
        return ProductResponse.model_validate(product_dict)

    name = update_fields.get("name")
    description = update_fields.get("description")
    price = update_fields.get("price")
    stock_quantity = update_fields.get("stock_quantity")

    product_dict = await update_product(
        product_id=product_id,
        name=name,
        description=description,
        price=price,
        stock_quantity=stock_quantity,
    )
    if product_dict is None:
        return None
    return ProductResponse.model_validate(product_dict)


async def delete_product_service(product_id: int) -> bool:
    deleted_id = await delete_product(product_id)
    return deleted_id is not None


async def bulk_update_stock_service(updates: list[tuple[int, int]]) -> None:
    if not updates:
        return
    await bulk_update_stock(updates)