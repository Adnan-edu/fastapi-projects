# Empty by design. Marks `app` as a Python package so `from app.main
# import app` works in uvicorn / pytest. Avoid putting code here — anything
# imported at package init time runs on every `import app.*`, which slows
# down test collection and creates surprising import-time side effects.
