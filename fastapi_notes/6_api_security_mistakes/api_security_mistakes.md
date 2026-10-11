https://levelup.gitconnected.com/7-api-security-mistakes-ive-seen-in-almost-every-python-backend-7f0fd0024625


## 1. Broken Object-Level Authorization (BOLA)

This is probably the first vulnerability because the introduction explicitly describes it.

### Typical Vulnerable Code

```python
@app.get("/users/{user_id}")
def get_user(user_id: int):
    return db.query(User).filter(User.id == user_id).first()
```

An authenticated user can request:

```http
GET /users/1
GET /users/2
GET /users/3
```

and retrieve data belonging to other users.

### Why It's Dangerous

Authentication verifies who the user is.

Authorization verifies what the user can access.

Many developers implement authentication but forget authorization.

### Common Impact

* View other users' profiles
* Access invoices
* Read private messages
* Download documents
* Access payment history

### Fix

Always filter by the authenticated user's identity.

```python
user = (
    db.query(User)
    .filter(User.id == current_user.id)
    .first()
)
```

Or explicitly check ownership.

```python
if resource.owner_id != current_user.id:
    raise HTTPException(status_code=403)
```

---

## 2. Broken Authentication

The article likely moves next into authentication weaknesses.

### Common Examples

#### Weak JWT Validation

```python
jwt.decode(token, SECRET)
```

without validating:

* expiration
* issuer
* audience
* signature algorithm

#### Never-Expiring Tokens

```python
payload = {
    "user_id": user.id
}
```

No expiration field.

### Risks

* Stolen tokens remain valid forever
* Session hijacking
* Account takeover

### Fixes

Use short-lived access tokens.

```python
{
    "sub": str(user.id),
    "exp": expiration_timestamp
}
```

Validate:

* exp
* iss
* aud

Rotate refresh tokens.

Store secrets securely.

---

## 3. Mass Assignment Vulnerabilities

Very common in Django, FastAPI, SQLAlchemy, and Pydantic applications.

### Vulnerable Example

```python
user = User(**request.json())
```

Suppose the frontend sends:

```json
{
  "name": "Alice",
  "email": "alice@test.com",
  "is_admin": true
}
```

The attacker discovers the hidden field and submits it manually.

### Result

They become an administrator.

### Why It Happens

Developers assume users only send fields visible in the UI.

Attackers never use your UI.

They use:

* Postman
* curl
* Burp Suite
* custom scripts

### Fix

Use allowlists.

```python
class UserCreate(BaseModel):
    name: str
    email: str
```

Explicitly assign fields.

```python
user = User(
    name=data.name,
    email=data.email
)
```

Never blindly unpack request payloads.

---

## 4. Excessive Data Exposure

This appears in many APIs.

### Vulnerable Endpoint

```python
return user.__dict__
```

or

```python
return user
```

when the ORM object contains sensitive fields.

Response:

```json
{
  "id": 1,
  "email": "alice@example.com",
  "password_hash": "...",
  "is_admin": true,
  "last_login": "..."
}
```

### Risks

Leaking:

* password hashes
* internal IDs
* security flags
* audit information

### Fix

Use response schemas.

FastAPI:

```python
class UserResponse(BaseModel):
    id: int
    email: str
```

Django REST Framework:

```python
fields = ["id", "email"]
```

Return only necessary fields.

---

## 5. Lack of Rate Limiting

A classic issue.

### Vulnerable Endpoint

```python
POST /login
```

with unlimited requests.

### Attacker Behavior

```python
for password in wordlist:
    attempt_login()
```

### Consequences

#### Credential Stuffing

Using leaked passwords from other breaches.

#### Brute Force

Trying thousands of passwords.

#### Denial of Service

Overwhelming API resources.

### Fixes

Rate limiting.

Examples include:

* Redis-based throttling
* API gateway limits
* Per-IP restrictions
* Per-user restrictions

FastAPI tools:

* SlowAPI
* custom middleware

Django tools:

* django-ratelimit

---

## 6. Security Misconfiguration

Often described as the "silent killer."

### Examples

#### DEBUG Enabled

```python
DEBUG = True
```

in production.

#### Open Swagger Docs

```python
/docs
```

available publicly.

#### Verbose Errors

```json
{
  "error": "SQLAlchemyError at line 212..."
}
```

#### Default Credentials

```text
admin/admin
```

still active.

### Risks

Attackers learn:

* database structure
* framework versions
* server configuration
* internal architecture

### Fixes

Production hardening checklist:

* Disable debug mode
* Hide stack traces
* Secure secrets
* Restrict admin panels
* Limit documentation exposure
* Enable HTTPS everywhere

---

## 7. Broken Function-Level Authorization

Often confused with BOLA.

### BOLA

Accessing another user's object.

Example:

```http
GET /users/5
```

instead of your own.

### Function-Level Authorization

Accessing a privileged action.

Example:

```http
POST /admin/delete-user
```

while being a normal user.

### Vulnerable Code

```python
@app.delete("/users/{id}")
def delete_user(id: int):
    ...
```

Authentication exists.

Authorization does not.

### Impact

Normal users can:

* delete accounts
* issue refunds
* modify roles
* access admin features

### Fix

Role-based access control.

```python
if current_user.role != "admin":
    raise HTTPException(status_code=403)
```

Or use permissions systems.

Examples:

* Django Permissions
* Django Guardian
* Casbin
* Oso

---

# Additional Security Checks Often Mentioned

Many articles conclude with a checklist.

### Input Validation

Validate:

* types
* lengths
* formats

Use:

* Pydantic
* Django Forms
* DRF Serializers

---

### SQL Injection Prevention

Bad:

```python
query = f"""
SELECT * FROM users
WHERE email = '{email}'
"""
```

Good:

```python
User.objects.filter(email=email)
```

or

```python
session.query(User).filter(User.email == email)
```

---

### Secrets Management

Avoid:

```python
SECRET_KEY = "hardcoded"
```

Use:

* environment variables
* secret managers
* vaults

---

### Logging and Monitoring

Track:

* failed logins
* permission failures
* token validation failures
* unusual traffic spikes

---

# The Core Message

The article's central argument is likely that most API breaches do **not** happen because attackers discover sophisticated zero-day vulnerabilities. They happen because developers focus on correctness and functionality while overlooking authorization, authentication, and exposure controls.

A backend can be:

* well-tested,
* cleanly architected,
* fully typed,
* highly performant,

and still be vulnerable if it doesn't rigorously enforce:

1. Object-level authorization (BOLA)
2. Authentication validation
3. Mass-assignment protection
4. Data exposure controls
5. Rate limiting
6. Secure configuration
7. Function-level authorization

These seven categories account for a large percentage of real-world API security incidents and align closely with the concerns highlighted by the OWASP API Security Top 10.

----

# 1. Broken Object-Level Authorization (BOLA)

## What It Is

A user can access another user's resource simply by changing an identifier.

This is one of the most common API vulnerabilities.

### Example Scenario

Imagine an e-commerce application.

User A:

```text
User ID: 101
```

User B:

```text
User ID: 102
```

Endpoint:

```http
GET /orders/102
```

If User A can retrieve User B's order by changing the ID, you have BOLA.

---

## Vulnerable FastAPI Example

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = db.query(User).filter(User.id == user_id).first()
    return user
```

### Attack

Authenticated user:

```http
GET /users/5
GET /users/6
GET /users/7
```

The API returns data for all users.

---

## Secure FastAPI Example

```python
@app.get("/users/{user_id}")
def get_user(user_id: int, current_user=Depends(get_current_user)):

    if current_user.id != user_id:
        raise HTTPException(403, "Forbidden")

    return current_user
```

---

## Vulnerable Django Example

```python
def user_profile(request, user_id):
    user = User.objects.get(id=user_id)
    return JsonResponse({
        "email": user.email
    })
```

---

## Secure Django Example

```python
@login_required
def user_profile(request, user_id):

    if request.user.id != user_id:
        return JsonResponse(
            {"error": "Forbidden"},
            status=403
        )

    return JsonResponse({
        "email": request.user.email
    })
```

---

# 2. Broken Authentication

## What It Is

Authentication mechanisms are weak or incorrectly implemented.

Common examples:

* Long-lived tokens
* Predictable session IDs
* Missing MFA
* Weak password policies
* JWT validation mistakes

---

## Vulnerable FastAPI JWT Example

```python
payload = jwt.decode(
    token,
    SECRET_KEY,
    algorithms=["HS256"]
)
```

Developer assumes this is enough.

But token expiration is never checked.

---

## Attack

Attacker steals token:

```text
Authorization: Bearer abc123
```

Months later:

```text
Still valid.
```

---

## Secure FastAPI JWT Example

```python
payload = jwt.decode(
    token,
    SECRET_KEY,
    algorithms=["HS256"],
    options={
        "verify_exp": True
    }
)
```

Generate short-lived tokens:

```python
expiration = datetime.utcnow() + timedelta(minutes=15)
```

---

## Vulnerable Django Example

```python
SESSION_COOKIE_AGE = 31536000
```

One-year session.

Compromised session remains active.

---

## Better Django Configuration

```python
SESSION_COOKIE_AGE = 1800
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
```

Also enable:

```python
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
```

---

# 3. Mass Assignment

## What It Is

The application automatically maps client input to database fields.

Attackers submit hidden fields that should never be editable.

---

## Example

Frontend form:

```json
{
  "name": "John"
}
```

Database model:

```python
class User:
    name
    email
    is_admin
```

Attacker sends:

```json
{
  "name": "John",
  "is_admin": true
}
```

---

## Vulnerable FastAPI Example

```python
data = request.json()

user = User(**data)
```

---

## Attack Result

```json
{
  "is_admin": true
}
```

Now user becomes administrator.

---

## Secure FastAPI Example

Use explicit schemas.

```python
class UserCreate(BaseModel):
    name: str
    email: str
```

Then:

```python
user = User(
    name=data.name,
    email=data.email
)
```

---

## Vulnerable Django Example

```python
for key, value in request.data.items():
    setattr(user, key, value)
```

---

## Secure Django Example

```python
class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = ["name", "email"]
```

Exclude:

```python
is_admin
role
is_staff
balance
```

---

# 4. Excessive Data Exposure

## What It Is

The backend returns more information than necessary.

---

## Vulnerable FastAPI Example

```python
@app.get("/me")
def me():
    return current_user
```

Response:

```json
{
  "id": 1,
  "email": "john@test.com",
  "password_hash": "...",
  "is_admin": false,
  "last_login": "..."
}
```

---

## Risks

Leaks:

* Internal flags
* Password hashes
* Access levels
* Security metadata

---

## Secure FastAPI Example

```python
class UserResponse(BaseModel):
    id: int
    email: str
```

```python
@app.get(
    "/me",
    response_model=UserResponse
)
def me():
    return current_user
```

---

## Vulnerable Django Example

```python
return JsonResponse(model_to_dict(user))
```

---

## Secure Django Example

```python
return JsonResponse({
    "id": user.id,
    "email": user.email
})
```

Or use serializers.

---

# 5. Broken Function-Level Authorization

## What It Is

User accesses functions they shouldn't.

Unlike BOLA, this targets actions rather than objects.

---

## Example

Normal user discovers:

```http
POST /admin/delete-user
```

The endpoint exists.

Authentication required.

Authorization missing.

---

## Vulnerable FastAPI Example

```python
@app.delete("/admin/users/{id}")
def delete_user(id: int):
    ...
```

---

## Attack

```http
DELETE /admin/users/42
```

Any authenticated user can delete accounts.

---

## Secure FastAPI Example

```python
@app.delete("/admin/users/{id}")
def delete_user(
    id: int,
    current_user=Depends(get_current_user)
):

    if current_user.role != "admin":
        raise HTTPException(403)

    ...
```

---

## Vulnerable Django Example

```python
@login_required
def delete_user(request, id):
    User.objects.filter(id=id).delete()
```

---

## Secure Django Example

```python
from django.contrib.auth.decorators import user_passes_test

@user_passes_test(lambda u: u.is_staff)
def delete_user(request, id):
    ...
```

---

# 6. Lack of Rate Limiting

## What It Is

API accepts unlimited requests.

Attackers can:

* Brute-force passwords
* Credential stuff
* Enumerate users
* Cause denial-of-service

---

## Vulnerable Login Endpoint

```python
@app.post("/login")
def login(credentials):
    ...
```

No limits.

---

## Attack

```python
for password in million_passwords:
    login(email, password)
```

---

## Secure FastAPI Example

Using SlowAPI:

```python
from slowapi import Limiter

limiter = Limiter()

@app.post("/login")
@limiter.limit("5/minute")
def login():
    ...
```

---

## Secure Django Example

Using django-ratelimit:

```python
@ratelimit(
    key="ip",
    rate="5/m",
    block=True
)
def login(request):
    ...
```

---

## Additional Protection

Limit by:

* IP
* User
* API key
* Endpoint

Store counters in:

* Redis
* Memcached

---

# 7. Security Misconfiguration

## What It Is

Application is deployed insecurely.

Often caused by development settings leaking into production.

---

## Example 1: Debug Mode

### Vulnerable Django

```python
DEBUG = True
```

Error page reveals:

```text
SQL queries
Filesystem paths
Installed apps
Environment details
```

---

### Secure Django

```python
DEBUG = False
ALLOWED_HOSTS = [
    "api.company.com"
]
```

---

## Example 2: Exposed Swagger

### Vulnerable FastAPI

```python
app = FastAPI()
```

Publicly exposes:

```text
/docs
/redoc
/openapi.json
```

---

### Secure FastAPI

```python
app = FastAPI(
    docs_url=None,
    redoc_url=None
)
```

Or protect docs with authentication.

---

## Example 3: Hardcoded Secrets

### Vulnerable

```python
SECRET_KEY = "mysecret123"
```

Committed to GitHub.

---

### Secure

```python
import os

SECRET_KEY = os.environ["SECRET_KEY"]
```

Or use:

* AWS Secrets Manager
* HashiCorp Vault
* Google Secret Manager
* Azure Key Vault

---

# 8. SQL Injection (Still Seen Frequently)

Although modern ORMs reduce risk, developers often reintroduce SQL injection.

---

## Vulnerable FastAPI Example

```python
query = f"""
SELECT *
FROM users
WHERE email = '{email}'
"""
```

Attacker:

```sql
' OR 1=1 --
```

Query becomes:

```sql
SELECT *
FROM users
WHERE email = '' OR 1=1 --
```

Returns all users.

---

## Secure FastAPI Example

```python
db.query(User).filter(
    User.email == email
)
```

---

## Vulnerable Django Example

```python
cursor.execute(
    f"SELECT * FROM users WHERE email='{email}'"
)
```

---

## Secure Django Example

```python
cursor.execute(
    "SELECT * FROM users WHERE email=%s",
    [email]
)
```

Or use ORM methods.

---

# Production Security Checklist

Before shipping a Django or FastAPI API, verify:

* ✅ Authentication exists
* ✅ Authorization enforced everywhere
* ✅ Object ownership validated
* ✅ Admin actions protected
* ✅ JWT expiration enforced
* ✅ Rate limiting enabled
* ✅ Input validation enforced
* ✅ Response schemas used
* ✅ Debug disabled
* ✅ HTTPS enforced
* ✅ Secrets externalized
* ✅ SQL parameterization used
* ✅ Logging and monitoring enabled
* ✅ Dependency scanning enabled
* ✅ Security testing included in CI/CD

A useful mental model is: **every value coming from the client is untrusted, every identifier in a URL can be manipulated, and every endpoint should assume an attacker is actively probing it.** Most real-world API breaches happen when one of those assumptions is forgotten.
