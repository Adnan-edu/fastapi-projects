from fastapi import APIRouter, HTTPException, Request, Response, status

from app.core.rate_limit import dynamic_plan_limit, get_api_key, limiter
from app.services import quote_service

router = APIRouter(prefix="/api/v1/quotes", tags=["quotes"])


@router.get("/", status_code=status.HTTP_200_OK)
@limiter.limit("10/minute")
def list_quotes(request: Request, response: Response):
    return {"quotes": quote_service.get_all()}


@router.get("/random", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute")
def random_quote(request: Request, response: Response):
    quote = quote_service.get_random()
    if not quote:
        raise HTTPException(status_code=404, detail="No quotes available")
    return quote


@router.get("/premium", status_code=status.HTTP_200_OK)
@limiter.limit(dynamic_plan_limit, key_func=get_api_key)
def premium_quotes(request: Request, response: Response):
    return {"quotes": quote_service.get_premium()}


@router.get("/{quote_id}", status_code=status.HTTP_200_OK)
@limiter.limit("5/minute", key_func=get_api_key)
def get_quote(request: Request, response: Response, quote_id: int):
    quote = quote_service.get_by_id(quote_id)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote