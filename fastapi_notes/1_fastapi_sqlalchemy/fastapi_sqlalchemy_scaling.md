# FastAPI + SQLAlchemy Performance Disaster

## “I Trusted SQLAlchemy with FastAPI. It Cost Me a Weekend”

This is a structured rewrite of the story with:

* problem statement
* root cause
* multiple examples
* debugging process
* solutions
* production best practices

---

# 1. The Initial Architecture

The developer built an API using:

* FastAPI
* SQLAlchemy
* PostgreSQL
* Pydantic response models

The goal was simple:

* clean architecture
* ORM-based database access
* nested API responses
* fast development

---

# 2. Initial Database Models

## Product Model

```python
from sqlalchemy.orm import relationship

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True)
    name = Column(String)

    categories = relationship(
        "Category",
        back_populates="product",
        lazy="select"
    )

    inventory = relationship(
        "Inventory",
        back_populates="product",
        lazy="select"
    )
```

---

## Category Model

```python
class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True)
    name = Column(String)

    product_id = Column(Integer, ForeignKey("products.id"))

    product = relationship(
        "Product",
        back_populates="categories"
    )
```

---

## Inventory Model

```python
class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True)
    stock = Column(Integer)

    product_id = Column(Integer, ForeignKey("products.id"))

    product = relationship(
        "Product",
        back_populates="inventory"
    )
```

---

# 3. The API Endpoint

Everything looked normal.

```python
@app.get("/products/{id}")
async def get_product(id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == id).first()
    return product
```

This seemed harmless.

---

# 4. The Response Model

The API returned nested objects.

```python
class CategoryResponse(BaseModel):
    id: int
    name: str


class InventoryResponse(BaseModel):
    id: int
    stock: int


class ProductResponse(BaseModel):
    id: int
    name: str
    categories: list[CategoryResponse]
    inventory: list[InventoryResponse]
```

---

# 5. The Hidden Problem Begins

The developer assumed:

```text
1 API request = 1 database query
```

But that assumption was wrong.

---

# 6. What Actually Happened

When FastAPI serialized the response:

```python
return product
```

Pydantic internally accessed:

```python
product.categories
product.inventory
```

Each access triggered a new SQL query because of:

```python
lazy="select"
```

---

# 7. The SQL Explosion

## First Query

```sql
SELECT * FROM products WHERE id = 1;
```

---

## Second Query

Triggered by:

```python
product.categories
```

SQL:

```sql
SELECT * FROM categories
WHERE product_id = 1;
```

---

## Third Query

Triggered by:

```python
product.inventory
```

SQL:

```sql
SELECT * FROM inventory
WHERE product_id = 1;
```

---

# 8. The N+1 Query Disaster

The problem became catastrophic with collections.

---

## Example Scenario

Suppose:

```text
100 products
Each product has:
- 5 categories
- 10 inventory records
```

---

## Code

```python
products = db.query(Product).all()
return products
```

---

# 9. What the Developer Expected

```text
1 query
```

---

# 10. What Actually Happened

## Query Count

```text
1 query -> load products

100 queries -> load categories
100 queries -> load inventory

TOTAL = 201 queries
```

This is called:

# N+1 Query Problem

---

# 11. Why Local Development Didn’t Reveal It

Local environment:

* tiny dataset
* localhost DB
* low latency
* no concurrent traffic

So everything appeared fast.

---

# 12. Production Symptoms

Under real traffic:

## Symptoms

* slow endpoints
* CPU spikes
* DB saturation
* connection pool exhaustion
* request timeouts
* cascading failures

---

# 13. The Most Dangerous Part

The SQL queries were invisible.

The endpoint looked innocent:

```python
return product
```

But serialization triggered hidden DB calls.

---

# 14. FastAPI + Pydantic Amplified the Issue

Serialization automatically accessed relationships.

Example:

```python
class ProductResponse(BaseModel):
    categories: list[CategoryResponse]
```

Pydantic reads:

```python
product.categories
```

which triggered SQLAlchemy lazy loading.

---

# 15. The Debugging Nightmare

The developer spent hours:

* checking PostgreSQL
* tuning indexes
* scaling DB connections
* investigating network latency

But the real issue was ORM loading behavior.

---

# 16. Root Cause

## Problem Statement

Using:

```python
lazy="select"
```

with nested FastAPI response serialization caused:

* uncontrolled implicit queries
* N+1 query explosions
* production performance collapse

---

# 17. The Correct Solution

Use:

* eager loading
* explicit relationship fetching
* query optimization

---

# 18. Solution #1 — `selectinload()`

## Recommended for collections

```python
from sqlalchemy.orm import selectinload

products = (
    db.query(Product)
    .options(
        selectinload(Product.categories),
        selectinload(Product.inventory)
    )
    .all()
)
```

---

# 19. What Happens Now

Instead of:

```text
201 queries
```

You get:

```text
1 query -> products
1 query -> categories
1 query -> inventory

TOTAL = 3 queries
```

Massive improvement.

---

# 20. Why `selectinload()` Works

SQLAlchemy batches related objects.

Example:

```sql
SELECT * FROM categories
WHERE product_id IN (1,2,3,4,5,...);
```

instead of:

```sql
SELECT * FROM categories WHERE product_id = 1;
SELECT * FROM categories WHERE product_id = 2;
SELECT * FROM categories WHERE product_id = 3;
```

---

# 21. Solution #2 — `joinedload()`

Useful for:

* one-to-one
* many-to-one
* smaller datasets

Example:

```python
from sqlalchemy.orm import joinedload

products = (
    db.query(Product)
    .options(joinedload(Product.inventory))
    .all()
)
```

---

# 22. Difference Between `joinedload` vs `selectinload`

| Feature              | joinedload    | selectinload |
| -------------------- | ------------- | ------------ |
| SQL JOIN             | Yes           | No           |
| Multiple Queries     | Usually 1     | Usually few  |
| Good for collections | Sometimes bad | Better       |
| Duplicate rows risk  | High          | Low          |
| Memory usage         | Higher        | Lower        |

---

# 23. Better Async Pattern

Another issue:

* sync SQLAlchemy inside async FastAPI endpoints

Bad:

```python
@app.get("/")
async def endpoint():
    db.query(...)
```

This blocks the event loop.

---

# 24. Better Modern Setup

Use:

* SQLAlchemy 2.0 async engine
* async sessions
* asyncpg

Example:

```python
from sqlalchemy.ext.asyncio import AsyncSession
```

---

# 25. Production Best Practices

## Always Monitor Query Counts

Enable SQL logging:

```python
engine = create_engine(
    DATABASE_URL,
    echo=True
)
```

---

## Use Profilers

Tools:

* Datadog
* New Relic
* OpenTelemetry
* pg_stat_statements

---

## Never Return Raw ORM Objects

Instead:

```python
return ProductResponse.model_validate(product)
```

with preloaded relationships.

---

## Explicitly Control Relationship Loading

Avoid implicit lazy loading unless absolutely necessary.

---

# 26. Final Architecture (Recommended)

## Models

```python
lazy="raise"
```

to prevent accidental lazy loads.

---

## Queries

```python
selectinload()
```

for collections.

---

## Async Database Access

```python
AsyncSession
```

---

## Explicit Serialization

Never rely on hidden ORM behavior.

---

# 27. Final Lesson

The core lesson is not:

> “SQLAlchemy is bad.”

The real lesson is:

> ORMs hide complexity extremely well.

At small scale:

* everything feels elegant

At production scale:

* hidden queries become catastrophic

The dangerous part is that the code still looks clean.

---

# 28. Recommended Reading

* FastAPI
* SQLAlchemy
* [SQLAlchemy Relationship Loading Docs](https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html?utm_source=chatgpt.com)
* [FastAPI Documentation](https://fastapi.tiangolo.com/?utm_source=chatgpt.com)
* [Original Medium Article](https://medium.com/@rameshkannanyt0078/i-trusted-sqlalchemy-with-fastapi-it-cost-me-a-weekend-5dabf581e3a1?utm_source=chatgpt.com)
