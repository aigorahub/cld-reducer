"""Exception types raised by cld-reducer."""


class CLDReducerError(Exception):
    """Base class for cld-reducer errors."""


class InvalidInputError(CLDReducerError, ValueError):
    """Raised when CLD input data is malformed or inconsistent."""


class SolverError(CLDReducerError, RuntimeError):
    """Raised when the optimization model cannot be solved."""
