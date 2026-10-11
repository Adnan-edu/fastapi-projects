# FastAPI Casbin Authorization — Document Management API

A hands-on learning project demonstrating **RBAC and ABAC authorization** in FastAPI using **Casbin**, built around a Document Management API where `admin`, `editor`, and `viewer` roles are enforced by declarative policy files rather than `if role == "admin"` checks scattered through route handlers.

The goal of this project is not to make a document app. It is to show how to move authorization *out of application code* and into a policy layer that is centralized, auditable, testable, and changeable without redeploying Python.

> **Why Casbin?** Casbin is the most widely adopted authorization library in the Python async ecosystem and it implements the **PERM metamodel** (Policy, Effect, Request, Matchers), which lets the same engine express ACL, RBAC, RBAC-with-resource-roles, ABAC, and RESTful models by editing two files. A simpler alternative such as **Guvnor** offers an easier API (decorators + a small role store) but far less flexibility — it cannot express subject/object attributes, role hierarchies, or custom matchers, and every new access pattern tends to become new application code.

---

## What You Will Learn

| Concept | Where it lives in this project |
|---|---|
| Authentication vs authorization separation | `app/core/auth.py` vs `app/core/casbin_enforcer.py` |
| Declarative policy (RBAC) | `app/policies/policy.csv` |
| Authorization *model* vs authorization *data* | `app/policies/model.conf` vs `app/policies/policy.csv` |
| FastAPI dependency-injected guards | `require_permission()` factory |
| Attribute-based (ownership) checks as a second tier | `update_document` / `delete_document` handlers |
| Policy-driven testing | `tests/test_authorization.py`, `tests/test_edge_cases.py` |

---

## Authentication vs Authorization

These two words are used interchangeably in casual conversation and must never be confused in code. This project implements only the second one properly.

| | **Authentication** | **Authorization** |
|---|---|---|
| Question | *Who are you?* | *What are you allowed to do?* |
| Answer source | Credentials (password, JWT, session, mTLS) | Roles, attributes, policies |
| Failure status | `401 Unauthorized` | `403 Forbidden` |
| This project | Faked: an `X-User` header resolves to a hard-coded user directory | Real: Casbin enforces every request |

Because authentication is deliberately faked with a single header, nothing in the codebase blocks swapping it for JWT validation later — that is the point of keeping the two in separate modules.

---

## The Domain Model

Three users, three documents, and four actions. Small enough to reason about exhaustively, which is exactly why it is good for studying authorization.

**Users** (`app/core/auth.py`):

| `X-User` header | Role |
|---|---|
| `alice` | `admin` |
| `bob` | `editor` |
| `carol` | `viewer` |

**Documents** (`app/services/document_service.py`), seeded so ownership checks are demonstrable:

| id | title | owner |
|---|---|---|
| 1 | Quarterly Report | `alice` |
| 2 | Meeting Notes | `bob` |
| 3 | Onboarding Guide | `alice` |

**Role → permission matrix** (this table is the *entire* security specification of the app, and it is enforced by 8 lines of CSV):

| Role | `read` | `create` | `update` | `delete` |
|---|---|---|---|---|
| `admin` | ✅ | ✅ | ✅ any document | ✅ any document |
| `editor` | ✅ | ✅ | ⚠️ **own** documents only | ❌ |
| `viewer` | ✅ | ❌ | ❌ | ❌ |

Note the ⚠️ cell. It is the single place where role alone is not enough to make a decision, and it is the reason this project has two authorization tiers instead of one.

---

## Tech Stack

- **Python ≥ 3.11** (`pyproject.toml`), FastAPI, Uvicorn
- **Casbin ≥ 1.38** — policy engine (no database adapter; files only)
- **Pydantic v2** — request/response schemas
- **pytest + httpx** — API-level tests via `TestClient`
- **uv** — virtualenv and dependency management

Verified against: Python 3.13.14, fastapi 0.141.1, casbin 1.43.0, pydantic 2.13.5, httpx 0.28.1, pytest 9.1.1.

---

## High-Level Architecture

There are exactly five moving parts, and each has one job. The two boxes on the right of the diagram are **data** — no Python logic whatsoever — which is what makes this design auditable by a non-developer.

```mermaid
flowchart TD
    Client["Client<br/>curl / Swagger UI / SDK"]

    subgraph FastAPI["FastAPI application"]
        Router["APIRouter<br/>/api/v1/documents"]
        Authn["Authentication layer<br/>app/core/auth.py<br/>get_current_user"]
        Guard["Authorization guard<br/>app/core/casbin_enforcer.py<br/>require_permission(obj, act)"]
        Handler["Route handler<br/>routes_documents.py"]
        Owner["Tier-2 ABAC check<br/>document.owner == user.username"]
        Service["Service layer<br/>app/services/document_service.py<br/>in-memory store"]
    end

    subgraph Policy["Policy layer — declarative data"]
        Model["model.conf<br/>HOW decisions are made"]
        CSV["policy.csv<br/>WHAT is allowed<br/>8 rules"]
    end

    Client -->|"HTTP + X-User header"| Router
    Router --> Authn
    Authn -->|"User(username, role)"| Guard
    Guard -->|"enforce(role, obj, act)"| Model
    Model --> CSV
    Guard -->|"403 Forbidden"| Client
    Guard -->|"allowed"| Handler
    Handler --> Owner
    Owner -->|"403 not your document"| Client
    Owner -->|"authorized"| Service
    Service -->|"Document / list"| Client
```

The layering matters more than the specific boxes:

1. **Transport** (`routes_documents.py`) knows about HTTP: paths, verbs, status codes, Pydantic models. It contains no permission logic beyond *declaring which permission each endpoint needs*.
2. **Authentication** (`auth.py`) turns a credential into an identity. It is the only module that knows what a user is.
3. **Authorization** (`casbin_enforcer.py`) turns an identity into a yes/no decision. It is the only module that knows what a role may do, and it never touches HTTP paths.
4. **Policy data** (`model.conf`, `policy.csv`) is the source of truth. Changing who can do what is a data edit, not a code change.
5. **Business logic** (`document_service.py`) performs the operation, unaware that authorization exists.

---

## Low-Level Request Lifecycle

The same picture, expressed as the exact call sequence for `PUT /api/v1/documents/2` sent by `bob`. FastAPI dependencies resolve **before** the handler body executes, and the ordering of those resolutions is the ordering of your security guarantees.

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as FastAPI
    participant A as get_current_user
    participant P as require_permission closure
    participant E as Casbin Enforcer
    participant H as update_document handler
    participant S as document_service

    C->>F: PUT /api/v1/documents/2 (X-User: bob, body)
    F->>A: resolve dependency (Header alias "X-User")
    A->>A: FAKE_USERS["bob"] lookup
    A-->>F: User(username="bob", role="editor")
    F->>P: resolve dependency (closure obj="document", act="update")
    P->>E: enforce("editor", "document", "update")
    E->>E: match model.conf matcher against policy.csv
    E-->>P: True
    P-->>F: User (dependency value = the authenticated user)
    F->>H: call handler(doc_id=2, body, user)
    H->>H: payload non-empty? document exists? owner == "bob"?
    H->>S: update_document(2, title, content)
    S-->>H: Document(id=2, ...)
    H-->>C: 200 OK + DocumentResponse
```

And the rejection path, which short-circuits two steps earlier — the handler is *never entered*:

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant F as FastAPI
    participant A as get_current_user
    participant P as require_permission closure
    participant E as Casbin Enforcer

    C->>F: DELETE /api/v1/documents/1 (X-User: bob)
    F->>A: resolve dependency
    A-->>F: User(username="bob", role="editor")
    F->>P: resolve dependency (obj="document", act="delete")
    P->>E: enforce("editor", "document", "delete")
    E->>E: no matching policy line
    E-->>P: False
    P-->>C: HTTPException 403 "cannot delete document"
    Note over E: update_document / delete_document<br/>never execute, so no store mutation can occur
```

Two consequences of this design are worth internalizing:

- **Denial is cheap and total.** A denied request never reaches business logic, so there is no partially-applied side effect to clean up.
- **Authorization precedes existence checks.** `bob` deleting document `9999` (which does not exist) receives `403`, not `404`. The server refuses to answer questions from callers who are not allowed to ask them. This ordering is verified in `tests/test_edge_cases.py`.

---

## Inside Casbin: The PERM Metamodel

Casbin separates **how** a decision is computed from **what** the rules are. The "how" is the model file; the "what" is the policy file. Four concepts, named by the acronym **PERM**:

| Letter | Concept | File section | Meaning here |
|---|---|---|---|
| **P** | Policy | `[policy_definition]` | The shape of one rule: `p = sub, obj, act` |
| **E** | Effect | `[policy_effect]` | How multiple matching rules combine into one verdict |
| **R** | Request | `[request_definition]` | The shape of the question asked at runtime |
| **M** | Matchers | `[matchers]` | The boolean expression that decides whether a rule matches a request |

A fifth, optional piece sits alongside them: `[role_definition]`, which adds role inheritance via `g`.

### `model.conf` — line by line

```ini
[request_definition]
r = sub, obj, act

[policy_definition]
p = sub, obj, act

[role_definition]
g = _, _

[policy_effect]
e = some(where (p.eft == allow))

[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act
```

**`r = sub, obj, act`** declares that a request carries exactly three values. At every call site the values are supplied by `require_permission`:

```python
enforcer.enforce(user.role, obj, act)   # e.g. enforce("editor", "document", "update")
```

`sub` is a **role**, not a username — an important and slightly unusual choice explained in the next section. `obj` is a resource *type* (`"document"`), never an individual instance, which is why instance-level control must be handled separately.

The arity is a hard contract enforced at runtime: passing a fourth argument raises `RuntimeError: invalid request size` rather than silently ignoring it (verified on casbin 1.43.0).

**`p = sub, obj, act`** declares that each stored rule is a triple. There is no `eft` column here, so every rule in `policy.csv` is implicitly an `allow`. Denial is expressed by the *absence* of a rule, never by a `deny` rule. This "deny-by-default" shape is the safer default: a typo in the CSV can only remove access, never silently grant it.

**`g = _, _`** registers a two-argument role relation. The underscores mean "any two values"; concrete pairs come from `g, <member>, <role>` lines in the policy file. Here is the subtle part:

> **`policy.csv` contains no `g` lines at all.** The matcher still works, because Casbin's role manager returns `true` when both names are identical — `has_link("editor", "editor") → True`. The everyday case in this app is therefore *direct name matching*, not inheritance.

The `g` definition is loaded and available, but it is currently unused metadata. It becomes functional the moment a grouping line exists. Verified live:

```python
enf.enforce("editor", "document", "delete")        # False

enf.add_grouping_policy("editor", "admin")         # same as adding "g, editor, admin"
enf.enforce("editor", "document", "delete")        # True -> editor inherits admin's delete

enf.remove_grouping_policy("editor", "admin")
enf.enforce("editor", "document", "delete")        # False again
```

That three-line demo is the whole value proposition of a policy engine: privilege escalation and de-escalation are *data operations* performed on a live enforcer, with no code change and no redeploy.
**`e = some(where (p.eft == allow))`** is the classic "at least one matching allow" effect — the same semantics as Unix group permissions, where any matching grant wins. Casbin offers stricter alternatives which this project deliberately does not use:

| Effect | Semantics | When you would want it |
|---|---|---|
| `some(where (p.eft == allow))` | Any allow wins. **Used here.** | Simple allow-lists |
| `!some(where (p.eft == deny))` | Allow unless something denies | Deny-list modelling |
| `allow && !deny` | An explicit deny always beats an allow | Compliance scenarios needing veto rules |
| `priority(p.eft) \|\| deny` | First matching rule wins | Ordered, firewall-style rule sets |

**`m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act`** is the boolean matcher, evaluated once per `(request, policy-line)` pair:

- `g(r.sub, p.sub)` — the *subject check*. Prefixed with `g` so the role manager is consulted instead of a raw string comparison. This is what makes role inheritance possible.
- `r.obj == p.obj` — the *object check*. Plain equality, hence no wildcards and no per-ID granularity.
- `r.act == p.act` — the *action check*. Plain equality.

All three are joined with `&&`, so a line matches only when all three hold. If any single line matches, the effect returns `allow`; otherwise Casbin returns `False` and `require_permission` converts that into a `403`.

Because the matcher is an arbitrary expression evaluated by Casbin's engine, this one line is where the project's future ABAC capability lives — see the `r.sub == r.obj.owner` variant under [Production Hardening Path](#production-hardening-path).

---

## `policy.csv` — The Actual Security Rules

Eight lines. Read each as "role X may do Y to Z".

```csv
p, admin, document, read
p, admin, document, create
p, admin, document, update
p, admin, document, delete
p, editor, document, read
p, editor, document, create
p, editor, document, update
p, viewer, document, read
```

| Lines | Subject | Object | Actions | Effect |
|---|---|---|---|---|
| 1–4 | `admin` | `document` | `read`, `create`, `update`, `delete` | Full CRUD |
| 5–7 | `editor` | `document` | `read`, `create`, `update` | Cannot delete |
| 8 | `viewer` | `document` | `read` | Read-only |

Notice what is **not** here: no line says "editor may update only their own documents", and no line mentions any username. Both omissions are intentional — the missing ownership rule is handled by Tier 2 (see below), and the absent usernames exist because the request subject is a role, keeping the policy independent of the user directory.

Operationally, the CSV is read **once per process** into memory by the lazy singleton in `casbin_enforcer.py`. Editing the file has no effect on a running server until the process restarts or `enforcer.load_policy()` is called. No file watcher is enabled in this project.

---

## Two-Tier Authorization: RBAC First, ABAC Second

The project's central design decision is that role-based and attribute-based checks happen at **different layers**, in a fixed order, for different reasons.

```mermaid
flowchart TD
    Start(["PUT or DELETE /api/v1/documents/{id}"]) --> RBAC{"Tier 1 — Casbin RBAC<br/>enforce(role, 'document', action)"}
    RBAC -->|"False"| Deny403["403 Forbidden<br/>'cannot update document'"]
    RBAC -->|"True"| Payload{"Handler check<br/>title or content supplied?"}
    Payload -->|"no"| Unprocessable["422 Unprocessable Content"]
    Payload -->|"yes"| Exists{"Document exists?"}
    Exists -->|"no"| NotFound["404 Not Found"]
    Exists -->|"yes"| IsAdmin{"role == admin?"}
    IsAdmin -->|"yes"| Allowed["Proceed to service layer"]
    IsAdmin -->|"no"| Owner{"document.owner == user.username?"}
    Owner -->|"no"| DenyOwn["403 Forbidden<br/>'You can only update<br/>your own documents'"]
    Owner -->|"yes"| Allowed
    Allowed --> Result(["200 OK / 204 No Content"])
```

### Why split it?

| Concern | Decided by | Data source | Changeable without deploy? |
|---|---|---|---|
| *Can this role use this endpoint?* | Casbin matcher, inside a dependency | `policy.csv` | ✅ yes — reload/restart only |
| *May this user touch this specific record?* | A Python `if` in the handler | The record's `owner` field | ❌ no — code change |

**Tier 1 (RBAC)** answers a question that is static and enumerable: a `viewer` cannot `create`, an `editor` cannot `delete`. Expressing it as data makes sense because it is a *policy* fact, and policy facts change on business timelines ("we are letting viewers comment now"), not on release timelines.

**Tier 2 (ABAC)** answers a question that depends on the *runtime state of a resource*: does `bob` own document `2`? Casbin could express this — the matcher can reach the object — but doing so would require passing the whole `Document` (or at least its owner) into `enforce()` and would couple `policy.csv` to the storage schema. Keeping it as one explicit `if` in the handler keeps the CSV readable and makes the ownership rule greppable, which is worth a great deal during an audit.

The interaction between the two tiers is where the interesting cases live:

| Actor | Target document | Tier 1 (Casbin) | Tier 2 (ownership) | Result |
|---|---|---|---|---|
| `alice` (admin) | document 2 (owned by `bob`) | ✅ update allowed | bypassed — is admin | **200** |
| `bob` (editor) | document 2 (his own) | ✅ update allowed | ✅ owner matches | **200** |
| `bob` (editor) | document 3 (owned by `alice`) | ✅ update allowed | ❌ not the owner | **403** |
| `bob` (editor) | document 3 (owned by `alice`) | ❌ delete denied | never reached | **403** |
| `carol` (viewer) | any document | ❌ update denied | never reached | **403** |

Rows 3 and 5 both return `403` but for completely different reasons, and the `detail` strings distinguish them:

- `"You can only update your own documents"` — Tier 2 rejection
- `"User 'carol' with role 'viewer' cannot update document"` — Tier 1 rejection

Good error messages are part of an authorization design, not decoration: they are what an integrator sees when a request is rejected, and what a security reviewer reads when auditing logs.

The admin bypass, written as `if doc.owner != user.username and user.role != "admin"`, is deliberately explicit and hard-coded rather than expressed as "admin is exempt in the policy". It stays a single visible, greppable escape hatch. That is a trade-off you should consciously revisit in a real system: it means the policy file is *not* the complete story for update and delete, a fact worth documenting for whoever inherits the code.

---

## The Authorization Dependency Factory

Everything above converges in one small function plus one factory in `app/core/casbin_enforcer.py`:

```python
def get_enforcer() -> casbin.Enforcer:
    global _enforcer
    if _enforcer is None:
        _enforcer = casbin.Enforcer(str(_MODEL_PATH), str(_POLICY_PATH))
    return _enforcer


def require_permission(obj: str, act: str):
    async def _check(user: User = Depends(get_current_user)) -> User:
        enforcer = get_enforcer()
        if not enforcer.enforce(user.role, obj, act):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"User '{user.username}' with role '{user.role}' "
                f"cannot {act} {obj}",
            )
        return user

    return _check
```

Read it in three layers:

1. **`get_enforcer()` is a lazy module-level singleton.** Constructing an `Enforcer` means parsing `model.conf` and loading the CSV, so caching it in the module global `_enforcer` avoids doing that work per request. The trade-off is that the singleton is per-process: with `uvicorn --workers 4` you get four independent enforcers, each loading the same files. No locking is needed because construction is idempotent and happens outside concurrent request handling.
2. **`require_permission` is a closure factory, not a dependency.** Calling it returns a *new async dependency* with `obj` and `act` baked into the closure. `Depends(require_permission("document", "create"))` means the route never calls the enforcer itself — it declares a requirement and lets the framework satisfy it. Because these expressions are evaluated at **import time**, each route carries its own immutable guard.
3. **The dependency returns `User`, not `None`.** The guard doubles as the "who is calling?" injector, so handlers declare exactly one dependency and receive both authentication and authorization. That is why signatures read `user: User = Depends(require_permission("document", "update"))` — clean, self-documenting, and hard to forget, since dropping the dependency makes the `user` variable vanish.

Advantages of this pattern over scattered role checks:

| | Scattered `if user.role == ...` | `require_permission` + Casbin |
|---|---|---|
| Discovery | Grep every handler to learn the rules | Read 8 CSV lines |
| Adding a role | Edit many handlers, risk missing one | Add CSV rows |
| Testing | Must exercise HTTP to test permissions | Unit-test `enforcer.enforce(...)` directly |
| Failure mode | A missed check is an invisible hole | Missing dependency means no `user` → visible break |
| Auditability | Distributed across files | One table, one matcher |

The last row is the real win. With this pattern, a forgotten authorization check does not merely leave a gap — it breaks the handler, because the handler references a `user` that was never injected.

One honest trade-off: `enforcer.enforce(...)` is a **synchronous, CPU-bound** call invoked from inside an `async def` dependency, so it executes on the event loop. For a policy set of eight lines the cost is negligible (microseconds), and Casbin's matching is pure in-memory work with no I/O. At policy sizes in the tens of thousands, the enforcer should be wrapped with `run_in_threadpool`, or the dependency declared as a plain `def` so Starlette offloads it automatically. That is the idiomatic FastAPI fix, and it is noted here rather than implemented because the current scale does not warrant it.

---

## HTTP Status Contract

Every distinct outcome maps to a distinct status code. The ordering in the sequence diagrams is observable here: authorization failures appear *before* existence failures.

| Status | Meaning in this app | Triggered by | Example |
|---|---|---|---|
| `200 OK` | Authorized read/update succeeded | Handler completed | `GET /api/v1/documents/1` as `carol` |
| `201 Created` | Authorized create succeeded | Handler completed | `POST /api/v1/documents/` as `bob` |
| `204 No Content` | Authorized delete succeeded | Handler completed, empty body | `DELETE /api/v1/documents/3` as `alice` |
| `403 Forbidden` | Identity known, permission denied | Casbin Tier 1, or ownership Tier 2, or unknown user | `DELETE /api/v1/documents/1` as `bob` |
| `404 Not Found` | Permission granted, resource absent | Handler lookup | `GET /api/v1/documents/9999` as `carol` |
| `422 Unprocessable Entity` | Request malformed | Pydantic validation, or empty update payload, or missing `X-User` header | `PUT /api/v1/documents/1` with `{}` |

Three of these are worth spelling out because they surprise people:

**Missing `X-User` returns `422`, not `401`.** The header is declared as `Header(..., alias="X-User")` — required by FastAPI's validation layer, so its absence is a *schema* failure that never reaches `get_current_user`. A real system with JWT would return `401` here, because it would own the authentication decision instead of delegating it to the validator.

**Unknown `X-User` returns `403`, not `401`.** `get_current_user` treats "eve is not in the directory" as forbidden. Semantically murkier than `401`, but harmless in a teaching app; the important part is that the request stops there.

**`403` can precede `404`.** For `DELETE /api/v1/documents/9999` as `bob`, the response is `403` because the permission check is a *dependency* that runs before the handler. The server refuses to disclose whether the document exists to a caller who is not allowed to delete documents. This is a deliberate property of the layering, not a bug — and it is asserted in `tests/test_edge_cases.py`.

---

## API Reference

All document endpoints are mounted under `/api/v1/documents` and every one of them requires the `X-User` header.

| Method | Path | Required permission | Success | Request body |
|---|---|---|---|---|
| `GET` | `/health` | none (excluded from schema) | `200` | — |
| `GET` | `/api/v1/documents/` | `document:read` | `200` | — |
| `GET` | `/api/v1/documents/{doc_id}` | `document:read` | `200` | — |
| `POST` | `/api/v1/documents/` | `document:create` | `201` | `DocumentCreate` |
| `PUT` | `/api/v1/documents/{doc_id}` | `document:update` + ownership | `200` | `DocumentUpdate` |
| `DELETE` | `/api/v1/documents/{doc_id}` | `document:delete` + ownership | `204` | — |

### Schemas

```python
class DocumentCreate(BaseModel):
    title: str = Field(..., min_length=1)      # required, non-empty
    content: str = Field(..., min_length=1)    # required, non-empty


class DocumentUpdate(BaseModel):
    title: str | None = None                   # both optional -> partial update
    content: str | None = None


class DocumentResponse(BaseModel):
    id: int
    title: str
    content: str
    owner: str
```

`DocumentCreate` validates at the schema layer (`min_length=1` → `422` for `""`), while `DocumentUpdate` accepts empty fields structurally and the handler rejects a *payload with no usable field* — `if not body.title and not body.content` — so `{}` and `{"title": ""}` are both `422`. Note that `owner` is never accepted from the client: it is always taken from the authenticated user (`owner=user.username`), which is the single most important anti-tampering rule in the whole project. A client cannot create a document on someone else's behalf.

### Example responses

`GET /api/v1/documents/1` as `carol` → `200`:

```json
{
  "id": 1,
  "title": "Quarterly Report",
  "content": "Q4 revenue exceeded targets.",
  "owner": "alice"
}
```

`DELETE /api/v1/documents/1` as `bob` → `403`:

```json
{
  "detail": "User 'bob' with role 'editor' cannot delete document"
}
```

`PUT /api/v1/documents/3` as `bob` → `403` (passes Casbin, fails ownership):

```json
{
  "detail": "You can only update your own documents"
}
```

`GET /api/v1/documents/` with no header → `422`:

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["header", "X-User"],
      "msg": "Field required",
      "input": null
    }
  ]
}
```

---

## Six Verified Request Traces

Each trace below was executed against the app and the response recorded verbatim.

**1. `GET /api/v1/documents/` as `bob` → `200`** (happy path)

1. `get_current_user` reads the header → `FAKE_USERS["bob"]` → `User("bob", "editor")`
2. `require_permission("document", "read")` evaluates `enforce("editor", "document", "read")`
3. The matcher hits `p, editor, document, read` → `True`
4. The dependency returns the `User`; the handler calls `document_service.list_documents()`
5. `200` with the document list

**2. `DELETE /api/v1/documents/1` as `bob` → `403`** (Tier 1 denial)

1. `bob` → role `editor`
2. `enforce("editor", "document", "delete")` → no matching CSV line → `False`
3. `HTTPException(403, "User 'bob' with role 'editor' cannot delete document")`
4. The handler body never runs. `bob` cannot delete *his own* document either — exactly what `test_editor_cannot_delete_own_document` asserts.

**3. `PUT /api/v1/documents/3` as `bob` → `403`** (Tier 2 denial, the ABAC case)

1. `enforce("editor", "document", "update")` → `True` (Tier 1 passes)
2. The handler checks the payload is non-empty → passes
3. Document 3 exists, `owner == "alice"`
4. `doc.owner != "bob"` **and** `user.role != "admin"` → `403 "You can only update your own documents"`

**4. `DELETE /api/v1/documents/9999` as `bob` → `403`** (authorization before existence)

1. `enforce("editor", "document", "delete")` → `False`
2. `403` is returned before the handler ever looks up document `9999`
3. Contrast with `alice` on the same URL, which returns `404`: the admin passes Tier 1, so the handler can report the missing document honestly.

**5. `GET /api/v1/documents/` with no header → `422`**

1. FastAPI validates route parameters before calling dependencies
2. `X-User` is required → the request is rejected at the validation layer
3. `get_current_user` never executes

**6. `GET /api/v1/documents/` as `eve` → `403`**

1. The header is present, so validation passes
2. `get_current_user` finds no `eve` in `FAKE_USERS` → `403 "Unknown user: eve"`
3. The enforcer is never consulted — an unknown identity is not worth evaluating

Two smaller behaviors worth knowing, both verified: the username lookup is **case-sensitive**, so `X-User: Alice` is an unknown user (`403`), while the HTTP header *name* is case-insensitive per the HTTP spec, so `x-user: alice` works. And responses never leak the store directly: `response_model=list[DocumentResponse]` filters output through Pydantic, so fields added to `Document` later stay private unless explicitly added to the response model.

---

## Layer-by-Layer File Walkthrough

```text
app/
├── main.py                      # app factory, /health, router registration
├── api/routes_documents.py      # HTTP surface: paths, schemas, guard declarations
├── core/auth.py                 # identity: User dataclass + fake directory
├── core/casbin_enforcer.py      # decision: singleton enforcer + guard factory
├── services/document_service.py # state: in-memory CRUD store
└── policies/
    ├── model.conf               # HOW decisions are computed
    └── policy.csv               # WHAT is allowed (8 rules)
```

**`app/main.py`** — a `create_app()` factory (rather than a bare module-level app) so tests and tooling can build isolated instances. It registers the router under `/api/v1/documents`, adds a `GET /health` probe hidden from the OpenAPI schema with `include_in_schema=False`, and then exposes `app = create_app()` at import time for `uvicorn app.main:app`. Title and version are declared here, which is why `/docs` renders as "FastAPI Casbin Authorization - Document Management API".

**`app/core/auth.py`** — the only module that knows what a user *is*. `User` is a plain `@dataclass(username, role)` rather than a Pydantic model because it is never parsed from a request body. `FAKE_USERS` is a module-level dict standing in for a user table. `get_current_user` is an `async def` dependency taking `x_user: str = Header(..., alias="X-User")`; the `alias` maps the Python-friendly parameter name onto the HTTP header name, and `...` makes it required. This is the single seam to replace when moving to JWT: swap the body of this one function, keep the `User` return type, and nothing else changes.

**`app/core/casbin_enforcer.py`** — the only module that knows what a role may *do*. It resolves `model.conf` and `policy.csv` relative to its own file (`Path(__file__).resolve().parent.parent / "policies"`), which makes it robust to being launched from any working directory. It exports `get_enforcer()` and `require_permission(obj, act)`, and imports `User`/`get_current_user` from `auth.py`, so the dependency chain reads explicitly as *identity first, then decision*.

**`app/api/routes_documents.py`** — the HTTP surface. Four Pydantic models define the wire format, and five endpoints declare their permission by construction: you cannot accidentally add an endpoint *without* a Casbin check, because the guard **is** the dependency. Two payload-validation nuances are worth noting: the empty-update rejection uses `status.HTTP_422_UNPROCESSABLE_CONTENT` — Starlette's current name for `422`; the older `HTTP_422_UNPROCESSABLE_ENTITY` still resolves to `422` but now emits a `DeprecationWarning` — while schema violations such as a blank `title` are rejected automatically by FastAPI's request validation. Both surface as `422`. The ownership check appears in both `update_document` and `delete_document` with tailored messages; at larger scale it is a candidate for a shared `ensure_owner_or_admin()` helper, though inlining keeps each handler's complete decision path readable in one screen.

**`app/services/document_service.py`** — a module-level `dict[int, Document]` behind four CRUD functions plus `_reset_store()`. It imports nothing from FastAPI, Casbin, or `auth`, so the service layer is entirely ignorant of HTTP *and* of authorization — which is what lets it be tested and reasoned about in isolation. `_next_id` produces sequential IDs starting after the three seed documents. Because the store is mutated in place, the reset helper **rebinds** the module global (`_documents = {...}`) rather than clearing it — and since routes call `document_service.list_documents()` (an attribute lookup at call time) instead of caching the dict, that rebinding is immediately visible to them. The leading underscore on `_reset_store` marks it as test-only API.

**`app/policies/model.conf` / `policy.csv`** — covered in depth above. The split between the two files is the whole architectural idea: `model.conf` changes when your *authorization pattern* changes (RBAC → ABAC → priority rules), while `policy.csv` changes when your *business rules* change.

---

## Test Suite

39 tests, all passing, organized by the *kind of question* they answer rather than by endpoint. That grouping is deliberate: authorization bugs are usually prediction failures ("I assumed viewers could not do that"), so the tests are arranged to make the prediction table explicit.

```bash
pytest -v
```

```text
tests/test_authorization.py ................. 16 tests
tests/test_documents.py ......                6 tests
tests/test_edge_cases.py .................   17 tests
                                              39 total
```

| File | Class | What it pins down | Count |
|---|---|---|---|
| `test_authorization.py` | `TestAdminPermissions` | Admin can read, create, update *any* document, delete *any* document | 5 |
| | `TestEditorPermissions` | Editor can read/create and update own documents; **cannot delete at all** | 6 |
| | `TestViewerPermissions` | Viewer can read; cannot create, update, or delete | 5 |
| `test_documents.py` | `TestDocumentCRUD` | Seed data shape, ID assignment, partial updates, delete-then-404 | 6 |
| `test_edge_cases.py` | `TestABACOwnership` | Tier-2 ownership rejections and the admin bypass | 4 |
| | `TestAuthEdgeCases` | Missing header (`422`), unknown user (`403`) across verbs | 4 |
| | `TestNotFoundErrors` | `404` for get/update/delete of a nonexistent ID | 3 |
| | `TestValidationEdgeCases` | Blank fields, empty payloads, `owner` derivation from identity | 6 |

The two most valuable tests in the suite are the ones that look redundant at first glance:

```python
def test_editor_cannot_delete_document(self, client):
    response = client.delete("/api/v1/documents/1", headers={"X-User": "bob"})
    assert response.status_code == 403

def test_editor_cannot_delete_own_document(self, client):
    response = client.delete("/api/v1/documents/2", headers={"X-User": "bob"})
    assert response.status_code == 403
```

Document 2 is owned by `bob`, so the second test proves that *ownership never overrides a role restriction*. The two tiers are independent: passing the ownership check does not compensate for failing the role check. Without that second test, a refactor that made ownership the primary check would silently grant editors the ability to delete their own documents — a plausible-sounding feature that was never agreed to.

Similarly, `test_editor_cannot_update_another_editors_document` asserts on the *message* (`assert "own documents" in response.json()["detail"]`), not just the status code. Both Tier 1 and Tier 2 return `403`, so asserting only the code would not distinguish "you may never update" from "you may not update this one" — and the distinction is the whole point of the project.

### Test infrastructure

`tests/conftest.py` provides two fixtures:

```python
@pytest.fixture(autouse=True)
def reset_state():
    document_service._reset_store()
    yield
    document_service._reset_store()


@pytest.fixture
def client():
    os.makedirs("logs", exist_ok=True)
    from app.main import app
    return TestClient(app)
```

`reset_state` is `autouse=True` and resets **before and after** each test. Resetting before matters as much as resetting after: it means a test cannot be affected by a leak from a previous one, so failures are always reproducible in isolation. The store is process-global mutable state, and this fixture is what makes it behave like a per-test database.

`client` imports `app` *inside* the fixture rather than at module scope, so the import happens after the first `reset_state` has run. `TestClient` drives the real ASGI app in-process — full routing, dependency resolution, Pydantic validation, and Casbin enforcement — with no network socket and no running server. The `os.makedirs("logs", exist_ok=True)` line is a leftover from a sibling project's logging setup; it is harmless and creates an unused directory.

Because `TestClient` exercises the whole stack, the tests are effectively integration tests: `test_viewer_cannot_create_document` is not testing a mock, it is proving that a real `POST` from a viewer is refused. That is the correct level for authorization, where the bug is almost always a *wiring* mistake rather than a logic mistake.

### Testing policies without HTTP

`require_permission` is only half of the design — the other half is that the enforcer is directly callable, so permission rules can be tested in isolation:

```python
from app.core.casbin_enforcer import get_enforcer

def test_policy_matrix():
    enf = get_enforcer()
    assert enf.enforce("admin", "document", "delete") is True
    assert enf.enforce("editor", "document", "delete") is False
    assert enf.enforce("viewer", "document", "read") is True
    assert enf.enforce("viewer", "document", "create") is False
```

This runs in microseconds and needs no HTTP layer, which is exactly the payoff of moving policy out of code: the security matrix becomes a unit-testable table.

---

## Setup

```bash
cd 10_fastapi_casbin_authorization

# create and activate an environment
uv venv fastapi_casbin_env
source fastapi_casbin_env/bin/activate

# install runtime + dev dependencies (pytest, httpx)
uv pip install -e ".[dev]"

# or equivalently, from the lockfile
uv sync
```

Manual equivalent if you are not using `uv`:

```bash
python -m venv fastapi_casbin_env
source fastapi_casbin_env/bin/activate
pip install fastapi "uvicorn[standard]" casbin pytest httpx
```

Dependencies declared in `pyproject.toml`: `fastapi>=0.115.0`, `uvicorn[standard]>=0.32.0`, `casbin>=1.38.0`, plus `pytest>=8.0.0` and `httpx>=0.27.0` under the `dev` extra. `requires-python = ">=3.11"` — the `str | None` union syntax in the Pydantic models would also work on 3.10, but `from __future__ import annotations` is used in the service module for safety.

## Run

```bash
uvicorn app.main:app --reload
# open http://127.0.0.1:8000/docs
```

`app/main.py` exposes the module-level `app`, so the standard `module:attribute` form works. Swagger UI at `/docs` reads the `X-User` header requirement straight from the dependency signature, so you can execute every request from the browser; ReDoc is at `/redoc`, and the raw schema at `/openapi.json`. The `/health` endpoint is reachable but intentionally absent from the schema.

## Try It

Every request needs the `X-User` header. `alice` is an admin, `bob` an editor, `carol` a viewer.

```bash
# reader: any role can list
curl -H "X-User: carol" http://127.0.0.1:8000/api/v1/documents/

# editor creates; owner is taken from the header, never the body
curl -X POST http://127.0.0.1:8000/api/v1/documents/ \
  -H "X-User: bob" -H "Content-Type: application/json" \
  -d '{"title": "New Doc", "content": "Hello from bob"}'

# editor updates his own document 2 -> 200
curl -X PUT http://127.0.0.1:8000/api/v1/documents/2 \
  -H "X-User: bob" -H "Content-Type: application/json" \
  -d '{"title": "Renamed by bob"}'

# editor updates alice's document 3 -> 403 (ownership)
curl -X PUT http://127.0.0.1:8000/api/v1/documents/3 \
  -H "X-User: bob" -H "Content-Type: application/json" \
  -d '{"title": "Tampered"}'

# admin overrides ownership -> 200
curl -X PUT http://127.0.0.1:8000/api/v1/documents/3 \
  -H "X-User: alice" -H "Content-Type: application/json" \
  -d '{"title": "Admin Override"}'
```

The four authorization failures worth reproducing by hand, because they are the ones that teach the ordering:

```bash
# 403 - Tier 1: editor may never delete, not even his own document
curl -i -X DELETE -H "X-User: bob" http://127.0.0.1:8000/api/v1/documents/2

# 403 - permission is checked before existence, so no 404 leak
curl -i -X DELETE -H "X-User: bob" http://127.0.0.1:8000/api/v1/documents/9999

# 403 - unknown user, enforcer never consulted
curl -i -H "X-User: eve" http://127.0.0.1:8000/api/v1/documents/

# 422 - header missing entirely, rejected by request validation
curl -i http://127.0.0.1:8000/api/v1/documents/
```

To watch role inheritance work, add one line to `app/policies/policy.csv`, restart, and retry:

```csv
g, editor, admin
```

Editors can now delete documents, because `g(r.sub, p.sub)` resolves `editor` up to `admin`. Remove the line and the privilege disappears. No Python was edited in either direction.

## Adding a New Role or Permission

The workflow this architecture is designed around — three steps, none of which touch Python:

1. **Add the user** to `FAKE_USERS` in `app/core/auth.py` (this is authentication data, not policy data).
2. **Add the rules** to `app/policies/policy.csv`, e.g. `p, auditor, document, read`.
3. **Restart** the server so the singleton enforcer reloads the CSV.

Even better, do not add a user at all — add a `g` line and inherit: `g, auditor, viewer` gives the new role everything `viewer` has today and automatically follows any future change to `viewer`.

For a genuinely new *resource type*, reuse the existing guard without touching the policy engine:

```python
@router.get("/", response_model=list[CommentResponse])
async def list_comments(user: User = Depends(require_permission("comment", "read"))):
    ...
```

Then add `p, viewer, comment, read` to the CSV. The matcher is generic over `obj`, so nothing in `model.conf` or the enforcer changes.

---

## Design Trade-offs and Deliberate Simplifications

Every simplification below is intentional and has a known migration path. None of them are accidents.

| Simplification | Why it is here | What it would cost in production | Migration path |
|---|---|---|---|
| **`X-User` header as authentication** | Keeps focus on authorization; any client can claim to be `alice` | Total authentication bypass — the header is trivially forged | Replace the body of `get_current_user` with JWT decoding; nothing else changes |
| **In-memory dict store** | Zero setup; the app starts instantly | State is lost on restart and not shared across workers | Swap `document_service` for a repository backed by SQLAlchemy/asyncpg |
| **Object = resource *type*** (`"document"`) | Keeps `policy.csv` short and instance-independent | Cannot express "user A may read document 5 but not document 6" for readers | Pass the instance into the matcher, or move per-instance rules into the DB with a Casbin adapter |
| **Ownership checked in Python, not in Casbin** | Keeps the CSV schema-free; the rule stays greppable in one `if` | The policy file is no longer the complete security story — auditors must read code too | Add `r.obj_owner` to the request and `r.sub == r.obj_owner \|\| g(r.sub, "admin")` to the matcher |
| **`enforce()` called on the event loop** | Negligible at 8 policy lines; keeps the dependency readable | At very large policy sets, matching becomes measurable CPU time per request | Declare the guard as a plain `def` (Starlette offloads it to a threadpool) or use `run_in_threadpool` |
| **Per-process enforcer singleton, no watcher** | Simple and fast; one load per process | CSV edits need a restart; N workers hold N copies | Add a Casbin `Watcher` or reload on SIGHUP; use a DB adapter for shared state |
| **No policy administration API** | Policy changes go through code review | Runtime privilege changes require a deploy | Add admin endpoints calling `add_policy`/`remove_policy` (and persist them) |
| **No `deny` rules** | Deny-by-default via absence of `allow` is the safer shape | Cannot express targeted exceptions to a granted permission | Add an `eft` column and switch the effect to `allow && !deny` |
| **No audit log of decisions** | Decisions are returned, not recorded | No forensic trail of who attempted what | Log every `enforce()` call with subject, object, action, and verdict |

The honest summary: this project is a **correct, complete demonstration of RBAC with a taste of ABAC**, not a hardened authorization system. The value is in the seam placement — identity, decision, policy data, and business logic are separated cleanly enough that replacing any one of them does not disturb the others.

### Known warnings

The suite passes with two deprecation warnings from the test tooling, not from project code:

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
                            install `httpx2` instead.
DeprecationWarning: The anyio.abc.BlockingPortal alias is deprecated
```

Both come from new Starlette releases (verified on starlette 1.6.0 with httpx 0.28.1) and affect only `TestClient`. The application code is unaffected. When the ecosystem settles, `httpx` in the `dev` extra becomes `httpx2` and the warnings disappear — which is exactly why it is pinned as an extra rather than a hard dependency.

---

## Production Hardening Path

Ordered by the security value each step adds per unit of effort.

### 1. Real authentication (highest priority)

The `X-User` header is the one thing here that is actively dangerous. Because `get_current_user` is the only function that produces a `User`, this is a contained change:

```python
async def get_current_user(credentials=Depends(HTTPBearer())) -> User:
    payload = verify_jwt(credentials.credentials)   # signature, exp, aud
    role = await load_role(payload["sub"])
    return User(username=payload["sub"], role=role)
```

Note the discipline being preserved: the function still returns the same `User` type and still answers only *"who is this?"*. The role lookup moves to a real store, but the *decision* about what that role may do stays in Casbin.

### 2. Ownership in the Casbin model (full ABAC)

This is the change the README has been building toward. Pass the resource's attributes into `enforce()` and move the ownership rule into the matcher, so `policy.csv` becomes the single source of truth for update and delete:

```ini
[request_definition]
r = sub, obj, act, owner
```

```ini
[matchers]
m = g(r.sub, p.sub) && r.obj == p.obj && r.act == p.act && (r.owner == r.sub || g(r.sub, "admin"))
```

```python
enforcer.enforce(user.role, "document", "update", doc.owner)
```

The Python `if` disappears and the admin bypass becomes explicit policy. The costs are real and worth stating: the request arity changes, `require_permission` must accept per-request attributes, the ownership lookup has to happen *inside* the dependency (before the handler), and `model.conf` becomes materially harder to read. That readability trade-off is precisely why this project starts with the two-tier split.

### 3. Durable, shared policy storage

```python
import casbin_sqlalchemy_adapter

adapter = casbin_sqlalchemy_adapter.Adapter("postgresql://user:pass@host/db")
enforcer = casbin.Enforcer(str(_MODEL_PATH), adapter)
```

A DB-backed adapter means every worker reads one authoritative policy set, changes are visible to all workers, and a policy admin API becomes possible. Two cautions: keep the model file on disk (it is code, not data), and remember that policy changes must be persisted explicitly — `add_policy` on a file adapter does not write back unless `enforcer.save_policy()` is called.

### 4. Audit logging of decisions

Record the subject, object, action, verdict, and request correlation ID for every check. Denied requests are the interesting ones — a spike in `403`s for `document:delete` is a meaningful security signal, and in a regulated environment the trail of *attempted* access is a compliance requirement rather than a nicety.

### 5. Extend the matrix, not the code

With the seams in place, the remaining work is data: inheritance lines for an `auditor` or `team-lead` role, a `comment` or `project` object type, and parametrized tests over the full role × action matrix. The 39 tests here are shaped to make that expansion mechanical — every new role gets a class, every new object gets a permission.

---

## Project Structure

```text
10_fastapi_casbin_authorization/
├── app/
│   ├── __init__.py
│   ├── main.py                       # create_app() factory, /health, router include
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes_documents.py        # 5 CRUD routes + Pydantic schemas + guards
│   ├── core/
│   │   ├── __init__.py
│   │   ├── auth.py                    # User dataclass, FAKE_USERS, get_current_user
│   │   └── casbin_enforcer.py         # enforcer singleton + require_permission factory
│   ├── policies/
│   │   ├── model.conf                 # PERM model: r, p, g, e, m
│   │   └── policy.csv                 # 8 allow rules (no g lines)
│   └── services/
│       ├── __init__.py
│       └── document_service.py        # in-memory store + _reset_store() test hook
├── tests/
│   ├── __init__.py
│   ├── conftest.py                    # client fixture + autouse state reset
│   ├── test_authorization.py          # role permission matrix (16 tests)
│   ├── test_documents.py              # CRUD happy paths (6 tests)
│   └── test_edge_cases.py             # ownership, authz edge cases, validation (17 tests)
├── pyproject.toml                     # deps, dev extra, pytest config (testpaths = tests)
├── uv.lock                            # resolved dependency lockfile
├── .gitignore
└── README.md
```

The layout follows the project series convention: `api/` for the HTTP surface, `core/` for cross-cutting concerns, `services/` for business logic, and a non-Python directory (`policies/`) for declarative configuration. There is no `models/` directory because the only persisted type lives beside the store that owns it, and no `db.py` because there is no database.

`pyproject.toml` also configures pytest with `testpaths = ["tests"]`, so a bare `pytest` from the project root collects the right directory regardless of where it is invoked from.

---

## Glossary

| Term | Meaning |
|---|---|
| **Authentication** | Establishing *who* a caller is. Faked here with `X-User`. |
| **Authorization** | Deciding *what* an authenticated caller may do. Real here, via Casbin. |
| **Subject (`sub`)** | The actor in a request. In this project it is a **role**, not a username. |
| **Object (`obj`)** | The resource a request targets. Here always the type `"document"`. |
| **Action (`act`)** | The operation requested: `read`, `create`, `update`, `delete`. |
| **Model (`model.conf`)** | Declarative definition of *how* decisions are computed (the PERM metamodel). |
| **Policy (`policy.csv`)** | Declarative data listing *which* `(sub, obj, act)` triples are allowed. |
| **Enforcer** | Casbin object that combines model + policy and answers `enforce(...)` calls. |
| **Matcher (`m`)** | The boolean expression comparing a request against each policy line. |
| **Effect (`e`)** | How matching results combine into a verdict (here: any allow wins). |
| **`g` / grouping policy** | Role-inheritance relation (`g, member, role`). Defined but unused in this project. |
| **RBAC** | Role-Based Access Control: permissions attach to roles, users inherit them. |
| **ABAC** | Attribute-Based Access Control: decisions consider resource/user attributes such as ownership. |
| **PERM** | Casbin's metamodel: Policy, Effect, Request, Matchers. |
| **Tier 1 / Tier 2** | This project's naming for the Casbin role check and the Python ownership check. |
| **Deny-by-default** | Absence of an `allow` rule means refusal. The default in this policy set. |

---

## Where This Fits in the Series

This is project **10** in a series that isolates one production concern per project and is the authorization counterpart to the surrounding projects. Related projects worth reading alongside it:

- **5_fastapi_redis_cache2** — caching decisions and idempotency keys, which pair naturally with a policy cache once `policy.csv` stops being tiny.
- **8_fastapi_prometheus_monitoring** — instrument the `403` rate as a first-class metric; authorization denials are a leading security indicator.
- **9_fastapi_loguru_structured_logging** — the natural home for authorization decision audit logs.
- **16_fastapi_logging** — the full observability stack, where per-request context and correlation IDs would let you trace a denial back to the individual request.

## Takeaways

1. **Authorization is data, not code.** Eight CSV lines describe the entire security policy of this application, and they can be reviewed by someone who has never seen the Python.
2. **Separate the "how" from the "what".** `model.conf` changes when your authorization *pattern* changes; `policy.csv` changes when your *business rules* change. Mixing those two concerns is what makes role checks rot.
3. **Role checks and instance checks belong at different layers.** Casbin decides what a role may do; application code decides whether *this* record is in scope. Keeping them apart keeps both legible.
4. **Make the guard impossible to forget.** Because `require_permission` returns the `User`, an endpoint without authorization has no `user` to work with — the failure is loud, not silent.
5. **Order your checks deliberately.** Authorization before existence disclosure is a decision you make once, in the dependency, rather than per-handler.
6. **Test the negative space.** Most of the 39 tests assert refusals, including the two that prove editors cannot delete even their *own* documents — the case where two authorization tiers are most likely to accidentally combine into a grant.