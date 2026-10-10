"""Shared reduction pipeline and strategy registry."""

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from .algorithms import letter_minimum
from .algorithms.assignment_minimum import (
    _build_model,
    _coverage,
    _selected_columns,
    _validate_solver_controls,
)
from .canonical import _solve_canonical
from .cliques import maximal_cliques
from .context import graph_context
from .display import _assign_letter_tokens, _format_letter_tokens
from .exceptions import InvalidInputError, SolverError
from .result import CLDReductionResult
from .validation import count_assignments, reconstruct_adjacency_from_assignments


@dataclass(frozen=True)
class Strategy:
    name: str
    aliases: tuple[str, ...]
    failure_prefix: str
    builder: Callable
    coverage: Callable
    decoder: Callable
    counts_assignments: bool


METHODS = (
    Strategy(
        "assignment_minimum",
        ("assignment_minimum", "assignment-minimum"),
        "assignment-minimum MILP failed: ",
        _build_model,
        _coverage,
        _selected_columns,
        True,
    ),
    Strategy(
        "letter_minimum",
        ("letter_minimum", "letter-minimum"),
        "letter-minimum MILP failed: ",
        letter_minimum.build_model,
        letter_minimum.coverage,
        letter_minimum.decode,
        False,
    ),
)


def check_method(method):
    for strategy in METHODS:
        if method in strategy.aliases:
            return strategy
    raise InvalidInputError(f"unsupported CLD reduction method: {method!r}")


def reduce_validated(adjacency, groups, means, strategy, time_limit, max_cliques):
    time_limit, max_cliques = _validate_solver_controls(time_limit, max_cliques)
    cliques = maximal_cliques(adjacency, max_cliques=max_cliques)
    model = strategy.builder(graph_context(adjacency, groups, means, cliques))
    selected, minimum = _solve_canonical(model, time_limit, strategy)
    columns = strategy.decoder(cliques, model, selected)
    tokens = _assign_letter_tokens(columns, len(groups), means, groups)
    assignments = dict(zip(groups, tokens, strict=True))
    letters = {g: _format_letter_tokens(t) for g, t in assignments.items()}
    if not np.array_equal(reconstruct_adjacency_from_assignments(assignments, groups), adjacency):
        raise SolverError("optimized letters did not preserve the input pairwise relationships")
    before = sum(map(len, cliques))
    after = count_assignments(assignments)
    if minimum != (after if strategy.counts_assignments else len(columns)):
        raise SolverError("HiGHS returned an invalid solution")
    return CLDReductionResult(
        letters=letters,
        assignments=assignments,
        stats={
            "assignments_before": before,
            "assignments_after": int(after),
            "reduction_pct": (before - after) / before * 100 if before else 0.0,
            "num_letters_before": len(cliques),
            "num_letters_after": len(columns),
            "num_groups": len(groups),
            "num_edges": len(model.edges),
            "solver_status": "Optimal",
            "objective": minimum,
        },
        method=strategy.name,
        groups=tuple(groups),
        relationship_preserved=True,
        adjacency=tuple(tuple(bool(v) for v in row) for row in adjacency),
    )
