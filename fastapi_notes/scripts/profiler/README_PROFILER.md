For a production-grade workflow, I would recommend a **Python-based interactive profiler wrapper** rather than a shell script because it is:

* Cross-platform (Linux/macOS, partial Windows support)
* Easier to extend
* Can validate prerequisites
* Can discover Python processes automatically
* Can generate flame graphs
* Can collect metadata
* Can archive profiling sessions
* Can handle permission and error cases gracefully

Below is a complete script that acts as an interactive front-end for `py-spy`.

# Features

✅ Detects py-spy installation

✅ Lists running Python processes

✅ Lets user choose target process

✅ Supports:

* top
* record
* dump

✅ Creates timestamped profiling sessions

✅ Stores logs

✅ Generates flame graphs

✅ Saves session metadata

✅ Handles missing permissions

✅ Handles dead processes

✅ Handles invalid selections

✅ Works with:

* FastAPI
* Flask
* Django
* Celery
* Streamlit
* Background workers
* Generic Python processes

---

# Example Workflow

Start FastAPI:

```bash
uvicorn app.main:app --reload
```

Run profiler:

```bash
python pyspy_profiler.py
```

Output:

```text
Running Python Processes

[1] PID=45231
    uvicorn app.main:app --reload

Select process number: 1
```

Choose:

```text
[1] Live Top View
[2] Record Flame Graph
[3] Stack Dump
```

Generate flame graph:

```text
Select option: 2
```

Load-test endpoint:

```bash
hey -n 10000 -c 100 \
http://localhost:8000/api/orders
```

Stop recording:

```text
Ctrl+C
```

Result:

```text
pyspy_sessions/
└── profile_45231_20260830_210300/
    ├── flamegraph.svg
    └── metadata.json
```

Open:

```bash
open pyspy_sessions/.../flamegraph.svg
```

(macOS)

or

```bash
xdg-open pyspy_sessions/.../flamegraph.svg
```

(Linux)

---

# Production Improvements

For a truly enterprise-grade profiler wrapper, I would additionally implement:

1. Automatic Docker container discovery
2. Kubernetes pod selection (`kubectl exec`)
3. Gunicorn worker discovery
4. Continuous sampling mode
5. Profiling duration limits
6. Automatic flame graph archiving
7. Integration with Prometheus/Grafana
8. CPU and memory snapshot collection
9. Async FastAPI dashboard UI
10. Automatic generation of profiling reports (HTML/PDF)

These additions turn the script from a simple wrapper into a full performance investigation toolkit suitable for FastAPI, Django, Flask, Celery, and large-scale Python services.
