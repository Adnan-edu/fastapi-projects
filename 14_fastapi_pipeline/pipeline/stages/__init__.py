"""Re-export the concrete stages so callers can do:

    from pipeline.stages import DbKeysetSource, NdjsonSink, Projection

instead of importing from each submodule individually. The names are listed
in `__all__` so `from pipeline.stages import *` (e.g. in REPL exploration)
gives you exactly the documented stages and nothing else.
"""

from pipeline.stages.chunk import Rechunk
from pipeline.stages.filter import PredicateFilter
from pipeline.stages.sink import CsvSink, NdjsonSink
from pipeline.stages.source import DbKeysetSource
from pipeline.stages.transform import Enrich, Projection

__all__ = [
    "CsvSink",
    "DbKeysetSource",
    "Enrich",
    "NdjsonSink",
    "PredicateFilter",
    "Projection",
    "Rechunk",
]
