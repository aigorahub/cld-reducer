#!/usr/bin/env python3
"""JSONL benchmark adapter. See PROTOCOL.md. No runtime source is changed.

Use one process per source repository and presolve setting. Native inputs are built
before timing. Only profile/preprocess/capture install temporary hooks. The command
writes responses to stdout and never opens an output file.
"""

from __future__ import annotations

import argparse
import importlib
import json
import platform
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import replace
from importlib.metadata import version
from pathlib import Path

PHASES = (
    "input",
    "vertex_reduction",
    "enumeration",
    "decision_plan",
    "model_construction",
    "essential_scan",
    "adapter_setup",
    "model_load",
    "initial_optimization",
    "canonical_trials",
    "output_expansion",
    "final_validation",
    "total",
)


@contextmanager
def patch_attributes(changes):
    """Restore the exact original objects, including after a failed installation."""
    originals = []
    try:
        for owner, name, value in changes:
            originals.append((owner, name, getattr(owner, name)))
            setattr(owner, name, value)
        yield
    finally:
        for owner, name, value in reversed(originals):
            setattr(owner, name, value)


def normalize(result):
    """Keep every public value and preserve group order, including empty labels."""
    groups = list(result.groups)
    return {
        "groups": groups,
        "assignments": [list(result.assignments[group]) for group in groups],
        "letters": [result.letters[group] for group in groups],
        "adjacency": [list(row) for row in result.adjacency],
        "method": result.method,
        "relationship_preserved": result.relationship_preserved,
        "stats": dict(result.stats),
        "rows": result.to_frame().to_dict(orient="records"),
    }


class Runtime:
    def __init__(self, repo, presolve="on"):
        self.repo = Path(repo).resolve(strict=True)
        source = self.repo / "python" / "src"
        if not (source / "cld_reducer" / "__init__.py").is_file():
            raise ValueError(f"Python source is absent from {source}")
        if presolve not in ("on", "off"):
            raise ValueError("presolve must be on or off")
        existing = sys.modules.get("cld_reducer")
        if existing and Path(existing.__file__).resolve().parent != source / "cld_reducer":
            raise RuntimeError("Use a fresh driver process for each source repository")
        sys.path.insert(0, str(source))
        # The package imports highspy eagerly. Load it first to measure that split.
        started = time.perf_counter_ns()
        self.highspy = importlib.import_module("highspy")
        self.solver_load_ns = time.perf_counter_ns() - started
        started = time.perf_counter_ns()
        self.package = importlib.import_module("cld_reducer")
        self.module_load_ns = time.perf_counter_ns() - started
        self.np = importlib.import_module("numpy")
        self.pd = importlib.import_module("pandas")
        self.api = importlib.import_module("cld_reducer.api")
        self.reduction = importlib.import_module("cld_reducer.reduction")
        self.solver = importlib.import_module("cld_reducer._solver")
        self.solver.settings.presolve = presolve
        self.presolve = presolve
        self.source_head = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def versions(self):
        h = self.highspy
        return {
            "language": "python",
            "runtime": platform.python_version(),
            "package": self.package.__version__,
            "dependencies": {name: version(name) for name in ("numpy", "pandas", "highspy")},
            "solver": {
                "name": "HiGHS",
                "version": ".".join(
                    str(getattr(h, name))
                    for name in (
                        "HIGHS_VERSION_MAJOR",
                        "HIGHS_VERSION_MINOR",
                        "HIGHS_VERSION_PATCH",
                    )
                ),
            },
            "module_load_ns": self.module_load_ns,
            "solver_load_ns": self.solver_load_ns,
            "load_notes": [
                "highspy import precedes package import; module_load_ns excludes it",
                "No solver instance or reduction is created by version",
            ],
            "settings_kind": "declared_contract",
            "settings_notes": "Profiles record actual native solver options",
            "settings": {
                "presolve": self.presolve,
                "threads": 1,
                "mip_rel_gap": 0.0,
                "mip_abs_gap": 0.0,
                "primal_feasibility_tolerance": 1e-9,
                "mip_feasibility_tolerance": 1e-9,
                "output_flag": False,
            },
            "source_head": self.source_head,
            "source_path": str(self.repo),
        }

    def prepare(self, case):
        if not isinstance(case, dict):
            raise ValueError("case must be an object")
        options = case.get("options")
        inputs = case.get("input")
        if not isinstance(options, dict) or not isinstance(inputs, dict):
            raise ValueError("case input and options must be objects")
        if options.get("method") not in ("letter_minimum", "assignment_minimum"):
            raise ValueError("case options must specify letter_minimum or assignment_minimum")
        options = dict(options)
        means = inputs.get("means")
        # Conformance means use rows. A mapping is also a public native input.
        if isinstance(means, list):
            means = self.pd.DataFrame(means)
        if case.get("call") == "adjacency":
            # dtype=object preserves mixed types for the public validator.
            try:
                matrix = self.np.array(inputs["adjacency"], dtype=object)
            except ValueError:
                matrix = inputs["adjacency"]
            return (
                self.package.reduce_from_adjacency,
                (matrix,),
                {
                    "groups": inputs.get("groups"),
                    "means": means,
                    **options,
                },
            )
        if case.get("call") == "pairs":
            return self.package.reduce_letters, (inputs["pairs"],), {"means": means, **options}
        raise ValueError("case call must be adjacency or pairs")

    def measure(self, prepared, iterations):
        if isinstance(iterations, bool) or not isinstance(iterations, int) or iterations < 1:
            raise ValueError("iterations must be a positive integer")
        call, args, kwargs = prepared
        started = time.perf_counter_ns()
        for _ in range(iterations):
            result = call(*args, **kwargs)
        elapsed = time.perf_counter_ns() - started
        return {"elapsed_ns": elapsed, "iterations": iterations, "result": normalize(result)}

    def capture(self, prepared):
        captured = {}
        original = self.reduction._solve_canonical

        def capture_solve(*args, **kwargs):
            selected, objective = original(*args, **kwargs)
            captured.update(selected=[int(value) for value in selected], objective=int(objective))
            return selected, objective

        with patch_attributes([(self.reduction, "_solve_canonical", capture_solve)]):
            call, args, kwargs = prepared
            result = call(*args, **kwargs)
        if not captured:
            raise RuntimeError("The runtime did not call the canonical capture hook")
        return {"result": normalize(result), "canonical": captured}

    def profile(self, prepared, preprocess=False):
        return Profile(self, preprocess).execute(prepared)

    def request(self, request):
        if not isinstance(request, dict):
            raise ValueError("request must be an object")
        action = request.get("action")
        if action == "version":
            return self.versions()
        if action not in ("measure", "capture", "profile", "preprocess"):
            raise ValueError(f"unknown action: {action!r}")
        prepared = self.prepare(request.get("case"))
        if action == "measure":
            return self.measure(prepared, request.get("iterations"))
        if action == "capture":
            return self.capture(prepared)
        return self.profile(prepared, preprocess=action == "preprocess")


class PreprocessComplete(Exception):
    """Stop at the canonical boundary without running an optimizer."""


class HighsProxy:
    """Forward native methods and observe model load and optimization only."""

    def __init__(self, native, profile):
        self.native = native
        self.profile = profile

    def __getattr__(self, name):
        return getattr(self.native, name)

    def passModel(self, *args, **kwargs):
        return self.profile.time_native("model_load", self.native.passModel, *args, **kwargs)

    def run(self, *args, **kwargs):
        result = self.profile.time_native("native_optimization", self.native.run, *args, **kwargs)
        self.profile.time_probe(self.observe)
        return result

    def observe(self):
        # Query counters after the native run timer. Never read solution values here.
        info = self.native.getInfo()
        counters = {}
        unavailable = {}
        for name in ("mip_node_count", "simplex_iteration_count", "ipm_iteration_count"):
            value = getattr(info, name, None)
            if value is None:
                unavailable[name] = "This highspy version does not expose this counter"
            elif value < 0:
                unavailable[name] = f"HiGHS reported unavailable ({value})"
            if name in unavailable:
                value = None
            counters[name] = value
        counters["unavailable"] = unavailable
        self.profile.native_counters.append(counters)
        values = {}
        for name in (*self.profile.runtime.solver.OPTION_NAMES, "output_flag"):
            option = self.native.getOptionValue(name)
            values[name] = option[1] if isinstance(option, tuple) else option
        time_limit = values.pop("time_limit")
        self.profile.native_settings.append(
            {
                "solve": len(self.profile.native_settings) + 1,
                "values": values,
                "excluded_values": {
                    "time_limit": time_limit if time_limit != float("inf") else None
                },
            }
        )


class HighspyProxy:
    def __init__(self, native, profile):
        self.native = native
        self.profile = profile

    def __getattr__(self, name):
        return getattr(self.native, name)

    def Highs(self, *args, **kwargs):
        return HighsProxy(self.native.Highs(*args, **kwargs), self.profile)


class Profile:
    def __init__(self, runtime, preprocess):
        self.runtime = runtime
        self.preprocess = preprocess
        self.phases = dict.fromkeys(PHASES)
        self.native_totals = {"model_load": 0, "native_optimization": 0}
        self.native_calls = dict.fromkeys(self.native_totals, 0)
        self.native_counters = []
        self.native_settings = []
        self.probe_ns = 0
        self.solve_records = []
        self.model = self.context = self.original_adjacency = self.reduced = None
        self.plan = None
        self.required = None
        self.canonical = None
        self.strategy = None
        self.enumeration_end = self.canonical_end = self.validation_start = None

    def time_native(self, phase, function, *args, **kwargs):
        started = time.perf_counter_ns()
        try:
            return function(*args, **kwargs)
        finally:
            self.native_totals[phase] += time.perf_counter_ns() - started
            self.native_calls[phase] += 1

    def time_probe(self, function):
        started = time.perf_counter_ns()
        try:
            return function()
        finally:
            self.probe_ns += time.perf_counter_ns() - started

    def builder(self, original):
        def wrapped(context):
            self.context = context
            started = self.enumeration_end or time.perf_counter_ns()
            self.model = original(context)
            self.phases["model_construction"] = time.perf_counter_ns() - started
            return self.model

        return wrapped

    def planner(self, original):
        def wrapped(context):
            self.context = context
            started = self.enumeration_end or time.perf_counter_ns()
            self.plan = original(context)
            self.phases["decision_plan"] = time.perf_counter_ns() - started
            return self.plan

        return wrapped

    def compiler(self, original):
        def wrapped(plan):
            started = time.perf_counter_ns()
            self.model = original(plan)
            self.phases["model_construction"] = time.perf_counter_ns() - started
            return self.model

        return wrapped

    def essentials(self, original):
        def wrapped(model):
            started = time.perf_counter_ns()
            self.required = original(model)
            self.phases["essential_scan"] = time.perf_counter_ns() - started
            return self.required

        return wrapped

    def hooks(self):
        runtime, reduction = self.runtime, self.runtime.reduction
        original_reduce = runtime.api.reduce_validated
        original_graph = reduction.reduce_graph
        original_enumerate = reduction.maximal_cliques
        original_canonical = reduction._solve_canonical
        original_validation = reduction.reconstruct_adjacency_from_assignments
        original_run = runtime.solver.run

        def reduce_validated(adjacency, *args, **kwargs):
            self.phases["input"] = time.perf_counter_ns() - self.started
            self.original_adjacency = adjacency
            try:
                return original_reduce(adjacency, *args, **kwargs)
            finally:
                if self.validation_start is not None:
                    self.phases["final_validation"] = time.perf_counter_ns() - self.validation_start

        def reduce_graph(*args, **kwargs):
            started = time.perf_counter_ns()
            self.reduced = original_graph(*args, **kwargs)
            self.phases["vertex_reduction"] = time.perf_counter_ns() - started
            return self.reduced

        def enumerate_cliques(*args, **kwargs):
            started = time.perf_counter_ns()
            result = original_enumerate(*args, **kwargs)
            self.enumeration_end = time.perf_counter_ns()
            self.phases["enumeration"] = self.enumeration_end - started
            return result

        def canonical(model, time_limit, strategy):
            self.strategy = strategy
            if self.preprocess:
                if self.plan is not None:
                    strategy.compiler(model)
                strategy.essential_decisions(model)
                raise PreprocessComplete
            selected, objective = original_canonical(model, time_limit, strategy)
            self.canonical = {
                "selected": [int(value) for value in selected],
                "objective": int(objective),
            }
            self.canonical_end = time.perf_counter_ns()
            return selected, objective

        def validation(*args, **kwargs):
            self.validation_start = time.perf_counter_ns()
            if self.canonical_end is not None:
                self.phases["output_expansion"] = self.validation_start - self.canonical_end
            return original_validation(*args, **kwargs)

        def run(*args, **kwargs):
            before = dict(self.native_totals)
            probes_before = self.probe_ns
            started = time.perf_counter_ns()
            outcome = original_run(*args, **kwargs)
            inclusive = time.perf_counter_ns() - started
            probes = self.probe_ns - probes_before
            self.solve_records.append(
                {
                    "status": outcome.status,
                    "elapsed_ns": inclusive - probes,
                    "probe_ns": probes,
                    "primary": kwargs.get("sum_limit") is None,
                    **{
                        name + "_ns": value - before[name]
                        for name, value in self.native_totals.items()
                    },
                }
            )
            return outcome

        strategies = tuple(
            replace(
                strategy,
                **(
                    {
                        "planner": self.planner(strategy.planner),
                        "compiler": self.compiler(strategy.compiler),
                    }
                    if hasattr(strategy, "planner")
                    else {"builder": self.builder(strategy.builder)}
                ),
                essential_decisions=self.essentials(strategy.essential_decisions),
            )
            for strategy in reduction.METHODS
        )
        return [
            (runtime.api, "reduce_validated", reduce_validated),
            (reduction, "reduce_graph", reduce_graph),
            (reduction, "maximal_cliques", enumerate_cliques),
            (reduction, "METHODS", strategies),
            (reduction, "_solve_canonical", canonical),
            (reduction, "reconstruct_adjacency_from_assignments", validation),
            (runtime.solver, "run", run),
            (runtime.solver, "highspy", HighspyProxy(runtime.highspy, self)),
        ]

    def execute(self, prepared):
        call, args, kwargs = prepared
        result = None
        reference_ns = None
        reference = None
        if not self.preprocess:
            started = time.perf_counter_ns()
            reference = call(*args, **kwargs)
            reference_ns = time.perf_counter_ns() - started
        with patch_attributes(self.hooks()):
            self.started = time.perf_counter_ns()
            try:
                result = call(*args, **kwargs)
            except PreprocessComplete:
                if not self.preprocess:
                    raise
            self.phases["total"] = time.perf_counter_ns() - self.started
        if (self.plan is None and self.model is None) or self.strategy is None:
            raise RuntimeError("The runtime did not call the model and canonical profile hooks")
        if not self.preprocess and self.canonical is None:
            raise RuntimeError("The runtime did not return a canonical vector")
        metrics = self.metrics()
        missing = {
            key: (
                "No optimization or output runs during preprocessing"
                if self.preprocess
                else "The runtime did not call this profile hook"
            )
            for key, value in self.phases.items()
            if value is None
        }
        response = {
            "profile_schema": 2 if self.plan is not None else 1,
            "metrics": metrics,
            "phases_ns": self.phases,
            "profile_notes": {
                "source_head": self.runtime.source_head,
                "source_patch": None,
                "full_call_overhead": None
                if self.preprocess
                else {
                    "instrumented_ns": self.phases["total"],
                    "uninstrumented_calls": 1,
                    "reference_ns": reference_ns,
                    "instrumented_minus_reference_ns": self.phases["total"] - reference_ns,
                    "ratio": self.phases["total"] / reference_ns if reference_ns else None,
                    "note": (
                        "One preceding uninstrumented full call. "
                        "The signed difference includes runtime noise and probe cost; "
                        "this reference difference is not subtracted."
                    ),
                },
                "instrumentation": "Temporary Python wrappers and a forwarding highspy proxy",
                "phase_unavailable": missing,
                "metric_unavailable": (
                    {
                        name: "No optimization runs during preprocessing"
                        for name in ("selected", "objective", "final_zero_decisions")
                    }
                    if self.preprocess
                    else {}
                ),
                "timing": [
                    "All times use perf_counter_ns; wrapper overhead is included",
                    "total includes the public API and hooks; it excludes conversion and metrics",
                    "solver_total_ns and trial times exclude measured native diagnostic probes",
                    "probe_ns includes only added settings/counter reads and record assembly",
                    "decision_plan includes graph_context and planning on the lazy runtime",
                    "model_construction measures compilation; legacy includes graph_context",
                    "initial_optimization is the initial native Highs.run call",
                    "canonical_trials sums later adapter calls with setup, load and native run",
                    "adapter_setup is adapter call time minus native load and native run",
                    "adapter_setup includes production assembly, options, reads and wrappers",
                    "model_load sums native passModel calls across all solves",
                    "final_validation includes relationship checks, statistics and result assembly",
                    "Stages overlap; do not sum phases or use profile total for acceptance",
                ],
            },
        }
        if self.model is None:
            response["profile_notes"]["metric_unavailable"].update(
                {
                    name: "Certificate returned before BIP compilation"
                    for name in ("auxiliary_variables", "constraints", "nonzeros")
                }
            )
        if not self.preprocess:
            response.update(result=normalize(result), canonical=self.canonical)
            if normalize(reference) != response["result"]:
                raise RuntimeError(
                    "Profile and uninstrumented reference returned different results"
                )
        return response

    def metrics(self):
        np = self.runtime.np
        problem = None if self.model is None else self.model.problem
        data = self.plan if self.plan is not None else self.model
        decisions = (
            list(range(self.plan.decision_count))
            if self.plan is not None
            else problem.decision_columns
        )
        essential_cover = None
        if self.required is not None:
            required = set(self.required)
            selected = np.asarray([column in required for column in decisions], dtype=bool)
            essential_cover = bool(self.strategy.coverage(data, selected))
        trials = [record for record in self.solve_records if not record["primary"]]
        first = [record for record in self.solve_records if record["primary"]]
        if self.native_calls["model_load"]:
            self.phases["model_load"] = self.native_totals["model_load"]
        if self.solve_records:
            self.phases["adapter_setup"] = sum(
                record["elapsed_ns"] - record["model_load_ns"] - record["native_optimization_ns"]
                for record in self.solve_records
            )
            self.phases["canonical_trials"] = sum(record["elapsed_ns"] for record in trials)
            if self.native_calls["native_optimization"]:
                self.phases["initial_optimization"] = sum(
                    record["native_optimization_ns"] for record in first
                )
        counters = {"available": bool(self.native_counters), "per_solve": self.native_counters}
        if not self.native_counters:
            counters["reason"] = "No native Highs.run call was observed"
        return {
            "vertices_before": len(self.original_adjacency),
            "vertices_after": len(self.reduced.adjacency),
            "edges": int(np.count_nonzero(np.triu(self.original_adjacency, 1))),
            "edges_after": len(self.context.edges),
            "maximal_cliques": len(self.context.cliques),
            "decision_variables": len(decisions),
            "model_compiled": problem is not None,
            "auxiliary_variables": None if problem is None else problem.num_cols - len(decisions),
            "constraints": None if problem is None else len(problem.row_lower),
            "nonzeros": None if problem is None else len(problem.value),
            "essential_decisions": None if self.required is None else len(self.required),
            "essential_cover": essential_cover,
            "solve_count": len(self.solve_records),
            "solver_total_ns": sum(record["elapsed_ns"] for record in self.solve_records),
            "probe_ns": self.probe_ns,
            "canonical_feasible_trials": sum(
                r["status"] == self.runtime.solver.OPTIMAL for r in trials
            ),
            "canonical_infeasible_trials": sum(
                r["status"] == self.runtime.solver.INFEASIBLE for r in trials
            ),
            "canonical_feasible_trials_ns": sum(
                r["elapsed_ns"] for r in trials if r["status"] == self.runtime.solver.OPTIMAL
            ),
            "canonical_infeasible_trials_ns": sum(
                r["elapsed_ns"] for r in trials if r["status"] == self.runtime.solver.INFEASIBLE
            ),
            "final_zero_decisions": None
            if self.canonical is None
            else self.canonical["selected"].count(0),
            "selected": None if self.canonical is None else self.canonical["selected"],
            "objective": None if self.canonical is None else self.canonical["objective"],
            "solver_settings": {
                "available": bool(self.native_settings),
                "records": self.native_settings,
                "source": "Native Highs.getOptionValue after each actual optimization",
                "excluded": "time_limit varies with the shared deadline; null means infinite",
            },
            "solver_counters": counters,
            "solve_records": self.solve_records,
        }


def serve(repo, presolve, input_stream=sys.stdin, output_stream=sys.stdout):
    runtime = None
    for line in input_stream:
        action = None
        try:
            request = json.loads(line)
            if isinstance(request, dict):
                action = request.get("action")
            if runtime is None:
                runtime = Runtime(repo, presolve)
            payload = runtime.request(request)
            response = {"ok": True, "action": action, **payload}
        except Exception as error:
            response = {
                "ok": False,
                "action": action,
                "error": {"kind": type(error).__name__, "message": str(error)},
            }
        try:
            encoded = json.dumps(
                response, ensure_ascii=False, allow_nan=False, separators=(",", ":")
            )
        except (TypeError, ValueError) as error:
            encoded = json.dumps(
                {
                    "ok": False,
                    "action": action,
                    "error": {"kind": type(error).__name__, "message": str(error)},
                }
            )
        output_stream.write(encoded + "\n")
        output_stream.flush()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--presolve", choices=("on", "off"), default="on")
    args = parser.parse_args()
    if not args.repo.is_absolute():
        parser.error("--repo must be an absolute path")
    serve(args.repo, args.presolve)


if __name__ == "__main__":
    main()
