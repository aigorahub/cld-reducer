"""Tools for reducing compact letter displays."""

from .api import reduce_from_adjacency, reduce_letters
from .exceptions import CLDReducerError, InvalidInputError, SolverError
from .result import CLDReductionResult

__version__ = "0.1.0"

__all__ = [
    "CLDReducerError",
    "CLDReductionResult",
    "InvalidInputError",
    "SolverError",
    "reduce_from_adjacency",
    "reduce_letters",
]
