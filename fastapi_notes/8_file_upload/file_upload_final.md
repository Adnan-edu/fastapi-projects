# File Uploads in Python APIs — From Broken to Bulletproof

*Your API shouldn't be a middleman between the browser and your storage.*

---

## Three Incidents in One Week

We launched a feature that let users upload profile pictures. The endpoint accepted a file, saved it to disk on the server, and returned the URL. It worked great in development. It worked fine in staging with three test users.

Then production happened. 2,000 users uploaded in the first week, and three things broke — each in a different way, all from the same ten lines of code.

**Incident 1 — Memory.** A user uploaded a 200MB file. It wasn't an image; it was a video they had accidentally selected. Our API held the entire file in memory while writing it to disk. With four Gunicorn workers and several large uploads landing at once, RAM hit 95% and unrelated requests started timing out.

**Incident 2 — Disk.** We had 20GB of local storage. Profile pictures accumulated without cleanup. When the disk hit 100%, Postgres could no longer write its WAL files. The entire application went down — not the upload feature, the *application*.

**Incident 3 — Security.** Someone uploaded a PHP file renamed to `.jpg`. Nginx happily served it. Nothing exploitable happened because we weren't running PHP, but the security review flagged it as critical — and they were right.

Three failures, one root cause: **we were treating file uploads as a simple feature when they are actually a distributed-systems problem.** Uploads touch memory, disk, network, security, and lifecycle management all at once. Any architecture that ignores even one of those dimensions will fail in production.

This article is the playbook we should have used from day one.

---

## The Broken Endpoint

Here's approximately what we shipped:

```python
from fastapi import FastAPI, UploadFile, File
import shutil

app = FastAPI()

@app.post("/upload/avatar")
async def upload_avatar(file: UploadFile = File(...)):
    destination = f"uploads/{file.filename}"
    with open(destination, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    return {"url": f"/media/{file.filename}"}
```

Every mistake is present in those ten lines:

1. **No size limit** — a 200MB video flows through unimpeded.
2. **Client-controlled filename** — path traversal (`../../etc/passwd`) is one POST away.
3. **Trust in extension** — `.jpg` proves nothing.
4. **Local disk as primary storage** — files are tied to a single server and accumulate forever.
5. **`shutil.copyfileobj`** — a synchronous call inside an async handler, blocking the event loop.
6. **No cleanup** — failed uploads, abandoned uploads, orphan files all linger.
7. **No metadata, no auth, no audit trail.**

This is the code that gets written when "file upload" is a one-day ticket. Let's fix it properly.

---

## Why the "Obvious" Fixes Don't Work

Before showing the right solution, it's worth dismissing the wrong ones — because they are the fixes most teams reach for first.

### Wrong fix #1: Check size after reading

```python
contents = await file.read()          # already 200MB in RAM
if len(contents) > MAX_SIZE:
    raise HTTPException(413, "Too large")
```

You have already consumed the memory. The reject is purely cosmetic.

### Wrong fix #2: Trust the extension

```python
if os.path.splitext(file.filename)[1].lower() not in {".jpg", ".png"}:
    raise HTTPException(400, "Invalid type")
```

A filename is a string the client controls. `malicious.php` becomes `malicious.jpg` with one keystroke. Extension checks are a UX hint, not a security control.

### Wrong fix #3: Trust the `Content-Type` header

The browser sends it. An attacker writes it. Same problem.

The actual fixes operate on **bytes that have arrived**, not on **strings the client claimed**. Let's build them.

---

## The Architecture That Works

Before the code, the picture. A production-grade upload pipeline has five distinct responsibilities, and a healthy system never confuses them:

```
┌──────────┐   1. presign / auth    ┌──────────┐
│  Client  │ ─────────────────────► │   API    │ ── 2. metadata ──► DB
└──────────┘                        └──────────┘
     │                                    │
     │ 3. PUT bytes directly              │ 4. async post-processing
     ▼                                    ▼
┌──────────────────┐               ┌──────────────────┐
│ Object Storage   │ ──5. events──►│ Worker (Celery)  │
│   (S3/GCS/R2)    │               │ scan / thumbnail │
└──────────────────┘               └──────────────────┘
     │
     │ 6. signed download / CDN
     ▼
┌──────────┐
│  Client  │
└──────────┘
```

Core principles, each of which corresponds to one of the failures above:

- **Never hold a full file in memory** — stream, and reject mid-stream.
- **Validate content, not claims** — magic bytes over MIME headers and extensions.
- **Separate compute from storage** — your API server is not a file server.
- **Make cleanup automatic** — pending state, lifecycle rules, orphan sweepers.
- **Defense in depth** — reverse proxy, application, storage policy, CDN — every layer enforces something.

Everything below implements one of those principles.

---

## Layer 1 — Stream in Chunks, Reject Mid-Stream

The fix for memory isn't checking after the fact. It's enforcing the limit *during* the read.

```python
from fastapi import FastAPI, UploadFile, File, HTTPException
import aiofiles
import uuid
import os

app = FastAPI()

MAX_UPLOAD_SIZE = 5 * 1024 * 1024   # 5MB
CHUNK_SIZE      = 64 * 1024         # 64KB


async def stream_to_temp(file: UploadFile) -> str:
    """Stream an upload to a temp file, enforcing the size cap byte-by-byte."""
    temp_path = f"/tmp/{uuid.uuid4().hex}"
    total = 0

    try:
        async with aiofiles.open(temp_path, "wb") as out:
            while chunk := await file.read(CHUNK_SIZE):
                total += len(chunk)
                if total > MAX_UPLOAD_SIZE:
                    raise HTTPException(413, "File exceeds 5MB limit")
                await out.write(chunk)
    except BaseException:
        # Clean up on any failure — HTTPException, cancellation, disk full, etc.
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise

    return temp_path
```

Three things this guarantees:

- Memory stays flat at ~64KB regardless of upload size.
- The upload is aborted at byte `MAX_UPLOAD_SIZE + 1`, not after.
- Temp files are removed on every failure path, not only the happy one.

Two implementation details worth being explicit about:

- **Use `aiofiles`, not `shutil.copyfileobj`.** The latter is synchronous and will block the FastAPI event loop for the duration of the write, starving every other coroutine on that worker.
- **`BaseException`, not `Exception`, in the cleanup handler.** `asyncio.CancelledError` is not an `Exception` in Python 3.8+; catching only `Exception` leaks temp files when clients disconnect mid-upload.

---

## Layer 2 — Validate Content, Not Claims

Every file format has a signature — a fixed-offset byte sequence called a **magic number**. JPEG starts with `FF D8 FF`. PNG starts with `89 50 4E 47 0D 0A 1A 0A`. PHP starts with `<?` or `<?php`. The OS does not care about the filename, and neither should you.

Install `python-magic`:

```bash
pip install python-magic
# Linux  (Debian/Ubuntu): apt-get install libmagic1
# macOS  (Homebrew):       brew install libmagic
# Windows:                 pip install python-magic-bin
```

Then inspect the bytes that landed in the temp file:

```python
import magic

ALLOWED_MIME_TYPES = {
    "image/jpeg": ".jpg",
    "image/png":  ".png",
    "image/webp": ".webp",
    "image/gif":  ".gif",
}


def validate_image(temp_path: str) -> str:
    """Return the MIME type after verifying the file is what it claims to be."""
    mime = magic.from_file(temp_path, mime=True)
    if mime not in ALLOWED_MIME_TYPES:
        os.unlink(temp_path)
        raise HTTPException(
            415,
            f"Unsupported file type '{mime}'. "
            f"Allowed: {', '.join(ALLOWED_MIME_TYPES)}"
        )
    return mime
```

For image uploads specifically, do a second pass with Pillow — magic bytes confirm the *header*, Pillow confirms the file is actually decodable (catches truncated files, parser bombs, polyglots):

```python
from PIL import Image, UnidentifiedImageError

def verify_image_decodes(temp_path: str) -> None:
    try:
        with Image.open(temp_path) as img:
            img.verify()                # parses headers, raises on tampering
    except (UnidentifiedImageError, Exception):
        os.unlink(temp_path)
        raise HTTPException(400, "Image file is corrupt or malformed")
```

And never write the client filename to disk. Generate your own:

```python
def safe_object_key(prefix: str, mime: str) -> str:
    ext = ALLOWED_MIME_TYPES[mime]
    return f"{prefix}/{uuid.uuid4().hex}{ext}"
```

The original filename, if you need it, goes into the database as **metadata**, never as a storage key.

---

## Layer 3 — Object Storage, Not Local Disk

Local disk is the wrong destination for user content. It fills up. It doesn't replicate. It ties files to a single host and turns horizontal scaling into a hostage situation. When it fills up, every disk-backed component on that host — including your database's WAL — fails with it. The correct destination is object storage: S3, GCS, Azure Blob, or an S3-compatible alternative like Cloudflare R2 or MinIO (great for local dev).

```python
import boto3
from botocore.exceptions import ClientError

s3 = boto3.client("s3", region_name=os.environ["AWS_REGION"])


def store_in_s3(temp_path: str, mime: str, prefix: str = "avatars") -> tuple[str, str]:
    """Upload the validated temp file to S3 and remove the temp file unconditionally."""
    bucket = os.environ["S3_BUCKET_NAME"]
    key = safe_object_key(prefix, mime)

    try:
        s3.upload_file(
            temp_path, bucket, key,
            ExtraArgs={
                "ContentType":  mime,
                "CacheControl": "max-age=31536000, immutable",
                "ServerSideEncryption": "AES256",
            },
        )
    except ClientError as e:
        raise HTTPException(502, "Storage backend rejected the upload") from e
    finally:
        if os.path.exists(temp_path):
            os.unlink(temp_path)        # always — success OR failure

    return key, f"https://{bucket}.s3.{os.environ['AWS_REGION']}.amazonaws.com/{key}"
```

The `finally` block is the most important line in this function. It is the reason your application server's disk does not fill up no matter how many uploads succeed or fail.

`boto3` is synchronous. If you are inside an async endpoint, wrap the call: `await asyncio.to_thread(store_in_s3, ...)`. Alternatively, use [`aioboto3`](https://pypi.org/project/aioboto3/) for fully async S3 calls.

---

## Layer 4 — Defense in Depth at the Edge

Application-layer limits are necessary but not sufficient. The reverse proxy should reject oversized requests **before they ever touch a Python worker**:

```nginx
# /etc/nginx/conf.d/uploads.conf
server {
    client_max_body_size      6m;     # slightly above app limit so a clean 413 wins
    client_body_buffer_size   128k;
    client_body_timeout       30s;
    keepalive_timeout         30s;

    location /upload/ {
        proxy_request_buffering off;   # stream to upstream, don't buffer to nginx disk
        proxy_pass http://app;
    }
}
```

Set the nginx limit slightly higher than the application limit. That way, requests that should hit the application's clean JSON 413 don't get a generic nginx HTML error page first.

---

## The Complete Validated Endpoint

Pulling layers 1–3 together into something you can ship:

```python
from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
import asyncio

app = FastAPI()

@app.post("/upload/avatar", status_code=201)
async def upload_avatar(
    file: UploadFile = File(...),
    user = Depends(get_current_user),
):
    temp_path = await stream_to_temp(file)           # Layer 1: bounded memory
    mime      = validate_image(temp_path)            # Layer 2: magic bytes
    verify_image_decodes(temp_path)                  # Layer 2: Pillow sanity
    key, url  = await asyncio.to_thread(             # Layer 3: object storage
        store_in_s3, temp_path, mime, f"avatars/{user.id}"
    )
    await save_avatar_metadata(user.id, key, url, mime, file.filename)
    return {"url": url, "key": key}
```

Each function does one thing. None of them holds more than 64KB in memory. None of them trusts a string the client provided. None of them leaves a temp file behind. Five lines of glue in the endpoint, and every one of the three incidents in the opening section is now impossible.

This would have survived the production launch as-is. But there is one further optimization — the one the subtitle of this article points at.

---

## Layer 5 — Get the API Out of the Upload Path Entirely

The endpoint above still has every uploaded byte transit your API server. For low-volume features (avatars, documents), that is fine. For anything heavier — video, datasets, large images, ML model artifacts — you are paying bandwidth and CPU on a machine whose job is *coordination, not transport*.

S3 supports **presigned URLs**: short-lived, cryptographically signed upload tokens you mint on your server and hand to the client. The client `PUT`s directly to S3. Your API server never sees the bytes.

There are two presigned variants, and the choice matters:

| Variant | When to use | How to enforce size |
| --- | --- | --- |
| `generate_presigned_url("put_object", …)` | Simple single-PUT uploads, easiest to consume from any HTTP client. | **Cannot enforce a size limit in the signature.** Rely on a bucket policy or post-upload validation. |
| `generate_presigned_post(…)` | When you need server-enforced size, content-type, or key constraints. | Use the `Conditions` parameter — S3 itself rejects oversize uploads at the storage layer. |

If you want size enforced before the upload completes, use `generate_presigned_post`:

```python
@app.post("/upload/avatar/presign")
async def presign_avatar_upload(
    content_type: str,
    user = Depends(get_current_user),
):
    if content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(400, f"Unsupported content type: {content_type}")

    ext = ALLOWED_MIME_TYPES[content_type]
    key = f"avatars/pending/{user.id}/{uuid.uuid4().hex}{ext}"

    presigned = s3.generate_presigned_post(
        Bucket=os.environ["S3_BUCKET_NAME"],
        Key=key,
        Fields={"Content-Type": content_type, "acl": "private"},
        Conditions=[
            {"Content-Type": content_type},
            {"acl": "private"},
            ["content-length-range", 1, MAX_UPLOAD_SIZE],   # S3 enforces this
        ],
        ExpiresIn=300,                                       # 5 minutes
    )
    return {"upload_url": presigned["url"], "fields": presigned["fields"], "key": key}
```

The client `POST`s to `upload_url` with the returned `fields` as form data plus the file. S3 rejects the upload with a 400 if it exceeds `MAX_UPLOAD_SIZE`, with a different content type than declared, or after the 5-minute window has expired.

After the upload completes, the client tells your API:

```python
@app.post("/upload/avatar/confirm")
async def confirm_avatar_upload(
    key: str,
    user = Depends(get_current_user),
):
    bucket = os.environ["S3_BUCKET_NAME"]

    # 1. Authorization: the key must live under this user's pending prefix.
    expected_prefix = f"avatars/pending/{user.id}/"
    if not key.startswith(expected_prefix):
        raise HTTPException(403, "Not your upload")

    # 2. Existence: the object actually landed in S3.
    try:
        head = s3.head_object(Bucket=bucket, Key=key)
    except ClientError:
        raise HTTPException(404, "Upload not found")

    # 3. Re-validate server-side: client-asserted content-type is not enough.
    #    Download the first 8KB and run python-magic over the real bytes.
    head_obj = s3.get_object(Bucket=bucket, Key=key, Range="bytes=0-8191")
    sniff   = head_obj["Body"].read()
    mime    = magic.from_buffer(sniff, mime=True)

    if mime not in ALLOWED_MIME_TYPES or head["ContentLength"] > MAX_UPLOAD_SIZE:
        s3.delete_object(Bucket=bucket, Key=key)
        raise HTTPException(400, "Upload rejected by post-validation")

    # 4. Promote: copy from pending/ to permanent location, then delete the pending object.
    final_key = key.replace("avatars/pending/", "avatars/", 1)
    s3.copy_object(
        Bucket=bucket,
        CopySource={"Bucket": bucket, "Key": key},
        Key=final_key,
        MetadataDirective="REPLACE",
        ContentType=mime,
        CacheControl="max-age=31536000, immutable",
    )
    s3.delete_object(Bucket=bucket, Key=key)

    cdn  = os.environ.get("CDN_BASE_URL", f"https://{bucket}.s3.amazonaws.com")
    url  = f"{cdn}/{final_key}"
    await update_user_avatar(user.id, url, final_key, mime)
    return {"url": url}
```

The flow from the client's perspective:

1. `POST /upload/avatar/presign` → receives upload form fields.
2. `POST {presigned.url}` directly to S3 with the form fields + file bytes — **your API server is not involved**.
3. `POST /upload/avatar/confirm` with the key → your API validates and promotes.

Your server handles two small JSON requests per upload. No file bytes, no memory spike, no bandwidth charge on the API server. The S3 layer enforces size at storage; your `confirm` handler enforces type after upload, before the file is promoted to its permanent location.

The `pending/` → permanent split is the lifecycle hook for cleanup: anything in `avatars/pending/` older than an hour is orphaned and can be deleted by an S3 lifecycle rule (more on this below).

---

## Massive Files: Multipart and Resumable Uploads

Single-PUT uploads above a few hundred megabytes are fragile. A dropped connection at 95% means starting from scratch. For uploads in the 500MB–multi-GB range, switch to **multipart**:

- The client splits the file into parts (typically 5–100MB each).
- Each part is uploaded independently and can be retried in isolation.
- Parts can upload in parallel for throughput.
- A final `CompleteMultipartUpload` call stitches them server-side.

S3 supports this natively (`create_multipart_upload`, `upload_part`, `complete_multipart_upload`), and the same presigned URL pattern works per-part. For browser clients, the [Uppy](https://uppy.io/) library + AWS Multipart plugin handles this with a few lines of JS; for resumable uploads over flaky networks (mobile clients especially), the [tus protocol](https://tus.io/) is the standard.

A pragmatic threshold:

| File size | Strategy |
| --- | --- |
| < 5MB | Streamed through API endpoint is fine. |
| 5MB – 100MB | Presigned single-PUT or POST. |
| 100MB – 5GB | Presigned multipart (parallel parts). |
| > 5GB | Multipart is **required** — single PUT is capped at 5GB on S3. |

---

## Post-Upload Processing

Validation gets the bytes to a safe resting place. Everything else — resizing, format conversion, virus scanning, content moderation, OCR, transcoding — belongs in a background worker, not the request path.

A common pipeline:

```python
from fastapi import BackgroundTasks

@app.post("/upload/avatar/confirm")
async def confirm_avatar_upload(key: str, bg: BackgroundTasks, user = Depends(get_current_user)):
    # ... validate & promote as above, get final_key ...
    bg.add_task(enqueue_postprocess, final_key, user.id)
    return {"url": url, "status": "processing"}
```

For anything heavier than a few seconds of CPU, use Celery, RQ, or Dramatiq instead of FastAPI's `BackgroundTasks` — `BackgroundTasks` runs in the same process and dies with it.

Typical processing steps:

- **Virus scan** with ClamAV (`clamd` over a Unix socket, or `aws-clamav-rest`). Mark the file as `scanned: clean | infected | error`; never serve unscanned uploads.
- **Thumbnail / resize** with Pillow or libvips (`pyvips`). Pillow is fine for small images; libvips is dramatically faster and more memory-efficient at scale.
- **Strip metadata** (EXIF, GPS) for privacy.
- **Re-encode** to a known-safe format. Re-encoding a JPEG to a JPEG removes most polyglot tricks.
- **Content moderation** via AWS Rekognition, Google SafeSearch, or an in-house model.

Triggering can be via S3 Event Notifications → SNS/SQS → worker, or via your confirm endpoint enqueueing directly. Event notifications are more reliable (they fire even if the client never calls `/confirm`), and they're how you catch direct-upload paths the API never sees.

---

## Secure Delivery — Never Expose Raw Storage

Public buckets are a category of breach unto themselves. Default to private storage and serve through one of:

- **Presigned download URLs** for private, time-limited access:

  ```python
  download_url = s3.generate_presigned_url(
      "get_object",
      Params={"Bucket": bucket, "Key": key},
      ExpiresIn=60,                # 60 seconds
  )
  ```

- **CDN with signed URLs or signed cookies** (CloudFront, Cloudflare) for high-traffic public content with revocation and access logs.
- **API-mediated download** for content that requires per-request authorization (e.g., paid content, role checks).

Whichever you choose, the rules are constant: short expiry, audit log, no public bucket ACLs, no listing permissions, no putting `Content-Disposition: inline` on user-uploaded HTML (you'd be reinventing stored XSS).

---

## Storage Lifecycle and Cleanup

Orphans are the silent failure mode of upload systems. Every upload that started but never finished, every confirm call that never came, every soft-deleted user whose files weren't purged — they all accumulate until your bill or your privacy review catches them.

Three mechanisms, layered:

**1. S3 lifecycle policies** — declarative, cheap, run on the storage side without any code:

```json
{
  "Rules": [
    {
      "ID": "expire-pending-uploads",
      "Status": "Enabled",
      "Filter": {"Prefix": "avatars/pending/"},
      "Expiration": {"Days": 1}
    },
    {
      "ID": "abort-incomplete-multipart",
      "Status": "Enabled",
      "Filter": {},
      "AbortIncompleteMultipartUpload": {"DaysAfterInitiation": 1}
    }
  ]
}
```

The second rule alone has saved more S3 bills than I can count — incomplete multipart parts are invisible in the console but billed in full.

**2. Orphan sweeper** — a nightly job that diffs object keys in S3 against keys referenced in the database, and deletes (or quarantines) anything in S3 with no DB row older than 24h. This catches direct-upload paths that succeeded on S3 but failed before reaching `/confirm`.

**3. Soft delete + grace period** — when a user deletes content, mark it deleted in the DB but keep the object for N days. Then a lifecycle rule removes it. This gives you a cheap undo and a defense against accidental cascading deletes.

---

## Observability

You cannot operate what you cannot see. Instrument every upload with:

- **Counters**: `uploads_started`, `uploads_succeeded`, `uploads_failed{reason}`, `uploads_rejected{reason}`.
- **Histograms**: upload size, upload duration, time-to-first-byte, processing latency.
- **Logs** (structured, one event per upload): `user_id`, `request_id`, `key`, `size`, `mime`, `result`, `duration_ms`.
- **Alerts**: error rate > 1%, p99 duration regression, sustained `413` spike (someone scripting against you), disk free < 20% on app hosts (catches Layer 1 leaks).

A surprisingly useful signal: alert when MIME-mismatch rejections cross a baseline. A sudden jump usually means a broken client release, not an attack — but you want to know either way within minutes, not from a support ticket.

---

## Production Readiness Checklist

Audit before shipping:

**Memory & I/O**
- [ ] No code path calls `await file.read()` without a size argument.
- [ ] All file writes use `aiofiles` (or are wrapped in `asyncio.to_thread`).
- [ ] Temp file cleanup uses `BaseException`, not `Exception`, and runs in `finally`.

**Validation**
- [ ] Size enforced during streaming, not after.
- [ ] MIME type derived from magic bytes (`python-magic`), not the client header.
- [ ] For images: Pillow `verify()` pass.
- [ ] Filenames are server-generated UUIDs; original filename is metadata only.
- [ ] EXIF / metadata stripped before serving (if privacy matters).

**Storage**
- [ ] No user content lives on application server disk.
- [ ] Bucket is private; access via presigned URLs or CDN with signed tokens.
- [ ] Server-side encryption (`AES256` or KMS) enabled.
- [ ] Lifecycle rule expires `pending/` prefix and aborts incomplete multipart uploads.

**Edge limits**
- [ ] Reverse proxy enforces `client_max_body_size` slightly above app limit.
- [ ] Per-user rate limit on upload endpoints.
- [ ] Presigned URL TTL ≤ 15 minutes.

**Lifecycle**
- [ ] `pending → permanent` promotion via `/confirm` flow.
- [ ] Orphan sweeper runs nightly.
- [ ] Soft-delete with grace period before object deletion.

**Security**
- [ ] Authentication required on presign and confirm endpoints.
- [ ] Authorization: confirm endpoint verifies the key belongs to the caller.
- [ ] Virus scan in the post-processing pipeline; uploads gated on `scanned: clean`.
- [ ] Re-validate MIME after direct upload (client claim is not enough).
- [ ] CSP / `Content-Disposition: attachment` for user-uploaded files served on your domain.

**Observability**
- [ ] Metrics, structured logs, alerts as above.
- [ ] Cost dashboards for storage and egress.

---

## The Summary Table

| Problem | Naive approach | What actually works |
| --- | --- | --- |
| Large-file memory spike | `await file.read()` then check size | Stream in 64KB chunks; reject at byte `MAX + 1` |
| Disk fills up | Save locally, hope for the best | Stream to temp, upload to S3, `finally: unlink` |
| Disguised file types | Check extension | Magic bytes via `python-magic` + Pillow verify |
| API bandwidth overhead | Route every byte through your server | Presigned POST/PUT — client uploads direct to S3 |
| Very large files | Single PUT until it breaks | Multipart upload, parallel parts, resumable (tus) |
| Orphaned uploads | Hope users finish them | `pending/` prefix + lifecycle rule + nightly sweeper |
| Public exposure | Public bucket, direct URLs | Private bucket, presigned download URLs or signed CDN |
| Unsafe content reaches users | Trust validation, serve immediately | Quarantine → scan → promote |

---

## The Mental Model

The mistake wasn't accepting file uploads. The mistake was treating file uploads like normal API requests.

JSON is small, structured, and belongs in application servers. Files are large, opaque, slow, and belong in object storage. The architecture should reflect that. Your API issues permissions and records metadata. Your storage layer stores bytes. Your worker layer transforms them. Each layer does one thing, and none of them is asked to do another layer's job.

A production-grade upload looks like this:

```
Browser                                          Object Storage
   │ ── presign request ──►  API ── token ──►  bytes go here ────► CDN
   │                          │                        │
   │                          ├──► metadata in DB      └──► event → worker
   │                          │                                 (scan, resize)
   │ ── confirm ─────────────►│
```

Your API handles authorization and metadata. Your storage system handles bytes. Your workers handle transformation. Your CDN handles delivery.

That's the difference between an upload feature that survives a demo and one that survives production.
