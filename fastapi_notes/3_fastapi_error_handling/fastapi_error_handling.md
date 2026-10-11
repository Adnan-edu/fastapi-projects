> FastAPI APIs should return structured, consistent, consumer-friendly error responses instead of random exceptions, raw stack traces, or inconsistent JSON shapes.

Here’s a reconstructed and expanded version of the likely content, organized step by step.

---

# FastAPI Error Handling That Actually Helps API Consumers

## The Problem With Default Error Handling

Most FastAPI beginners do this:

```python
from fastapi import FastAPI, HTTPException

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    if user_id != 1:
        raise HTTPException(status_code=404, detail="User not found")

    return {"id": 1, "name": "John"}
```

This works.

But real-world APIs become messy because:

* Different endpoints return different error shapes
* Validation errors look different from business logic errors
* Database failures expose internal details
* Frontend developers must handle many response formats
* Logs are inconsistent
* Swagger docs become unclear

This creates pain for API consumers. ([Better Stack][1])

---

# Goal: Consistent Error Responses

A production API should return a predictable structure.

Instead of this:

```json
{"detail": "User not found"}
```

and elsewhere:

```json
{"message": "Invalid token"}
```

and elsewhere:

```json
{"error": "Database failed"}
```

use one standard schema everywhere:

```json
{
  "success": false,
  "error": {
    "code": "USER_NOT_FOUND",
    "message": "User not found",
    "details": null
  }
}
```

---

# Step 1 — Create a Standard Error Model

```python
from pydantic import BaseModel
from typing import Optional, Any

class ErrorResponse(BaseModel):
    success: bool = False
    error: dict
```

Better version:

```python
class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Any] = None

class ErrorResponse(BaseModel):
    success: bool = False
    error: ErrorDetail
```

Now every error follows the same contract.

---

# Step 2 — Create Custom Exceptions

Instead of raising `HTTPException` everywhere:

```python
raise HTTPException(status_code=404, detail="User not found")
```

Create domain-level exceptions.

```python
class AppException(Exception):
    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details=None
    ):
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details
```

Then:

```python
class UserNotFound(AppException):
    def __init__(self):
        super().__init__(
            status_code=404,
            code="USER_NOT_FOUND",
            message="User not found"
        )
```

This keeps business logic clean.

---

# Step 3 — Global Exception Handler

FastAPI supports centralized exception handling. ([FastAPI][2])

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.exception_handler(AppException)
async def app_exception_handler(
    request: Request,
    exc: AppException
):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details
            }
        }
    )
```

Now all custom errors are standardized automatically.

---

# Step 4 — Handle Validation Errors Properly

FastAPI automatically returns validation errors, but the default format is often too verbose.

Example default:

```json
{
  "detail": [
    {
      "loc": ["body", "email"],
      "msg": "value is not a valid email",
      "type": "value_error.email"
    }
  ]
}
```

You can customize it.

```python
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):

    errors = []

    for err in exc.errors():
        errors.append({
            "field": ".".join(map(str, err["loc"])),
            "message": err["msg"]
        })

    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": errors
            }
        }
    )
```

Cleaner response:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Invalid request",
    "details": [
      {
        "field": "body.email",
        "message": "value is not a valid email"
      }
    ]
  }
}
```

---

# Step 5 — Handle Unexpected Exceptions

Never expose raw internal exceptions.

Bad:

```json
{
  "detail": "SQLAlchemy session exploded..."
}
```

Good:

```python
@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):

    # log actual error internally
    print(exc)

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Something went wrong"
            }
        }
    )
```

This prevents leaking:

* SQL queries
* stack traces
* infrastructure details
* secrets

---

# Step 6 — Add Logging

Centralized logging is critical. ([Better Stack][1])

```python
import logging

logger = logging.getLogger(__name__)

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):

    logger.exception("Unhandled exception occurred")

    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Unexpected error"
            }
        }
    )
```

---

# Step 7 — Use Error Codes

Error codes are better than only messages.

Why?

Frontend apps can reliably react to:

```json
"code": "TOKEN_EXPIRED"
```

instead of parsing text messages.

Examples:

| Code                 | Meaning                 |
| -------------------- | ----------------------- |
| USER_NOT_FOUND       | Missing user            |
| INVALID_TOKEN        | Auth token invalid      |
| RATE_LIMITED         | Too many requests       |
| EMAIL_ALREADY_EXISTS | Duplicate email         |
| VALIDATION_ERROR     | Input failed validation |

---

# Step 8 — Keep Swagger Documentation Clean

You can define response models:

```python
@app.get(
    "/users/{user_id}",
    responses={
        404: {"model": ErrorResponse},
        422: {"model": ErrorResponse},
    }
)
async def get_user(user_id: int):
    ...
```

This improves generated OpenAPI docs significantly.

---

# Recommended Production Structure

Example project layout:

```text
app/
├── exceptions/
│   ├── base.py
│   ├── handlers.py
│   └── user_exceptions.py
├── models/
│   └── error_models.py
├── routers/
├── services/
└── main.py
```

---

# Common Anti-Patterns

## 1. Returning HTTP 200 for Errors

Bad:

```json
{
  "success": false
}
```

with status code `200`.

Use proper HTTP codes:

* 400
* 401
* 403
* 404
* 422
* 500

Community consensus strongly prefers proper HTTP semantics. ([Reddit][3])

---

## 2. Exposing Internal Exceptions

Never return:

```python
str(exc)
```

to clients in production.

---

## 3. Inconsistent Response Shapes

Avoid:

```json
{"detail": "..."}
{"message": "..."}
{"error": "..."}
```

Use one schema.

---

# Complete Production Example

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

app = FastAPI()

class AppException(Exception):
    def __init__(self, status_code, code, message):
        self.status_code = status_code
        self.code = code
        self.message = message

class UserNotFound(AppException):
    def __init__(self):
        super().__init__(
            404,
            "USER_NOT_FOUND",
            "User not found"
        )

@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error": {
                "code": exc.code,
                "message": exc.message
            }
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(
        status_code=422,
        content={
            "success": False,
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Invalid request",
                "details": exc.errors()
            }
        }
    )

@app.get("/users/{user_id}")
async def get_user(user_id: int):

    if user_id != 1:
        raise UserNotFound()

    return {
        "success": True,
        "data": {
            "id": 1,
            "name": "John"
        }
    }
```

---

# Best Practices Summary

* Use centralized exception handling
* Create custom domain exceptions
* Standardize error schemas
* Use proper HTTP status codes
* Never expose internals
* Add structured logging
* Document responses in OpenAPI
* Make frontend handling predictable

---

Useful references:

* [FastAPI Official Error Handling Docs](https://fastapi.tiangolo.com/tutorial/handling-errors/?utm_source=chatgpt.com) ([FastAPI][2])
* [Better Stack FastAPI Error Handling Patterns](https://betterstack.com/community/guides/scaling-python/error-handling-fastapi/?utm_source=chatgpt.com) ([Better Stack][1])
* [FastAPI Interactive Tutorial: Handling Errors](https://www.fastapiinteractive.com/fastapi-basics/17-handling-errors?utm_source=chatgpt.com) ([fastapiinteractive.com][4])

[1]: https://betterstack.com/community/guides/scaling-python/error-handling-fastapi/?utm_source=chatgpt.com "FastAPI Error Handling Patterns | Better Stack Community"
[2]: https://fastapi.tiangolo.com/tutorial/handling-errors/?utm_source=chatgpt.com "Handling Errors - FastAPI"
[3]: https://www.reddit.com/r/FastAPI/comments/1flft9s/advice_needed_on_error_handling/?utm_source=chatgpt.com "Advice needed on error handling"
[4]: https://www.fastapiinteractive.com/fastapi-basics/17-handling-errors?utm_source=chatgpt.com "Handling Errors | FastAPI Basics | FastAPI Tutorial"
