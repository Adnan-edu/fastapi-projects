"""Public surface of the pipeline library.

Re-exporting from `__init__.py` keeps consumer imports short and stable:

    from pipeline import Pipeline, StageError

instead of forcing them to know that `Pipeline` lives in `core.py` and
`StageError` lives in `errors.py`. If we ever reorganize internally, the
public path stays the same.
"""

from pipeline.core import Pipeline, Source, Stage
from pipeline.errors import StageError

__all__ = ["Pipeline", "Source", "Stage", "StageError"]
