#!/usr/bin/env python3
"""Generate the cld-reducer conformance inputs, fixtures, and manifest by exact search.

Standard library only. The generator imports no package code and calls no solver. It
holds its own maximal clique code, its own exact search for the assignment-minimum
covering, and its own copy of the input rules of docs/algorithm.md, and it writes the
expected results that the Python, JavaScript, and R packages must reproduce.

    python3 conformance/generate.py --write   # write inputs, fixtures, manifest
    python3 conformance/generate.py --check   # regenerate in memory and compare

See conformance/README.md for the file formats and the pass rule.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INPUTS = ROOT / "inputs"
FIXTURES = ROOT / "fixtures"
MANIFEST = ROOT / "manifest.json"
PY_EXAMPLES = ROOT.parent / "python" / "examples"
DATA_FILES = [
    "piepho2004_wheat_pairs.csv",
    "simple_abc_to_ac_pairs.csv",
    "simple_abc_to_ac_means.csv",
]

SCHEMA_VERSION = 1
DEFAULT_MAX_CLIQUES = 10000
# Random graphs with more membership variables than this are left out (recorded in the
# manifest): the pure Python search is too slow on the densest ones.
MAX_RANDOM_VARIABLES = 70
RANDOM_SIZES = range(6, 13)
RANDOM_PER_SIZE = 40
RANDOM_SEED = 20261007
LABEL_COUNTS = [0, 1, 2, 3, 25, 26, 27, 28, 51, 52, 53, 54, 78, 701, 702, 703, 704, 730]


# ------------------------------------------------------------ small helpers ----

def splitmix64(seed):
    """Deterministic 64-bit generator; yields floats in [0, 1)."""
    state = seed & 0xFFFFFFFFFFFFFFFF
    while True:
        state = (state + 0x9E3779B97F4A7C15) & 0xFFFFFFFFFFFFFFFF
        z = state
        z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & 0xFFFFFFFFFFFFFFFF
        yield (z ^ (z >> 31)) / 2.0 ** 64


def shuffled(items, rng):
    """Fisher-Yates shuffle driven by a splitmix64 stream."""
    items = list(items)
    for i in range(len(items) - 1, 0, -1):
        j = int(next(rng) * (i + 1))
        items[i], items[j] = items[j], items[i]
    return items


def make_labels(count):
    """Spreadsheet labels A..Z, AA..AZ, BA.. (docs/algorithm.md section 7)."""
    out = []
    for index in range(count):
        value, label = index, ""
        while True:
            value, rem = divmod(value, 26)
            label = chr(ord("A") + rem) + label
            if value == 0:
                break
            value -= 1
        out.append(label)
    return out


def normalize_text(text):
    return text.replace("\r\n", "\n").replace("\r", "\n")


def read_text(path):
    """Read a text file with line ends normalized to LF (CRLF checkouts on Windows)."""
    with open(path, encoding="utf-8", newline="") as handle:
        return normalize_text(handle.read())


def sha256(text):
    return hashlib.sha256(normalize_text(text).encode("utf-8")).hexdigest()


def compact(obj):
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def dump_records(header, key, records):
    """JSON text with one record per line, so large files stay small and diffable."""
    head = compact(header)[:-1]
    lines = [head + ',"%s":[' % key]
    for i, rec in enumerate(records):
        lines.append(compact(rec) + ("," if i < len(records) - 1 else ""))
    lines.append("]}")
    return "\n".join(lines) + "\n"


def dump(obj):
    return json.dumps(obj, indent=1, ensure_ascii=True) + "\n"


# ------------------------------------------------------ maximal cliques/search ----

def maximal_cliques(n, adj):
    """All maximal cliques as ascending tuples, sorted lexicographically (spec section 3).

    Bron-Kerbosch with pivoting over bitmasks. `adj[i]` is the neighbor bitmask of i
    (without i).
    """
    found = []

    def expand(r, p, x):
        if p == 0 and x == 0:
            found.append(tuple(i for i in range(n) if r >> i & 1))
            return
        union = p | x
        pivot = max((u for u in range(n) if union >> u & 1),
                    key=lambda u: (p & adj[u]).bit_count())
        candidates = p & ~adj[pivot]
        for v in range(n):
            if candidates >> v & 1:
                expand(r | 1 << v, p & adj[v], x & adj[v])
                p &= ~(1 << v)
                x |= 1 << v

    expand(0, (1 << n) - 1, 0)
    return sorted(found)


class Model:
    """The covering problem of docs/algorithm.md section 4 and an exact search for it.

    A solution is a bitmask over the membership variables x[c, g], numbered in the
    canonical (clique, group) order of section 3. The y variables of the MILP are not
    needed: an edge is covered when some clique has both ends selected.
    """

    def __init__(self, n, edges):
        self.n = n
        self.edges = sorted((min(e), max(e)) for e in edges)
        nbr = [0] * n
        for i, j in self.edges:
            nbr[i] |= 1 << j
            nbr[j] |= 1 << i
        self.cliques = maximal_cliques(n, nbr)
        self.xs = [(c, g) for c, clique in enumerate(self.cliques) for g in clique]
        self.index = {v: k for k, v in enumerate(self.xs)}
        self.group_mask = [0] * n
        for k, (_, g) in enumerate(self.xs):
            self.group_mask[g] |= 1 << k
        self.constraints = []  # each: list of option masks; one must be inside the solution
        for i, j in self.edges:
            self.constraints.append(
                [1 << self.index[(c, i)] | 1 << self.index[(c, j)]
                 for c, clique in enumerate(self.cliques) if i in clique and j in clique])
        for g in range(n):
            self.constraints.append(
                [1 << k for k in range(len(self.xs)) if self.group_mask[g] >> k & 1])

    def search(self, fixed_in=0, fixed_out=0, limit=None):
        """Exact branch and bound over the covering constraints.

        Returns a solution mask that contains `fixed_in` and avoids `fixed_out`, or
        None. With `limit` None it returns a minimum solution; with a limit it returns
        the first solution of at most `limit` variables.
        """
        cons = [[pm for pm in options if not pm & fixed_out] for options in self.constraints]
        if any(not options for options in cons):
            return None
        best = [limit + 1 if limit is not None else len(self.xs) + 1]
        found = [None]
        seen = set()
        n, group_mask = self.n, self.group_mask

        def visit(sel):
            cost = sel.bit_count()
            if cost >= best[0] or sel in seen:
                return
            seen.add(sel)
            lacking = sum(1 for g in range(n) if not sel & group_mask[g])
            if cost + lacking >= best[0]:
                return
            open_cons = [o for o in cons if not any(sel & pm == pm for pm in o)]
            if not open_cons:
                best[0], found[0] = cost, sel
                return
            # Lower bound: open constraints whose candidate new variables are pairwise
            # disjoint need distinct new variables, so their cheapest costs add up.
            info = []
            for o in open_cons:
                new = 0
                cheapest = None
                for pm in o:
                    gain = pm & ~sel
                    new |= gain
                    count = gain.bit_count()
                    if cheapest is None or count < cheapest:
                        cheapest = count
                info.append((cheapest, new, len(o)))
            info.sort(key=lambda t: (-t[0], t[2]))
            used = bound = 0
            for cheapest, new, _ in info:
                if not new & used:
                    bound += cheapest
                    used |= new
            if cost + max(bound, lacking) >= best[0]:
                return
            pick = min(open_cons, key=len)
            for pm in sorted(pick, key=lambda pm: (pm & ~sel).bit_count()):
                visit(sel | pm)
                if limit is not None and found[0] is not None:
                    return

        visit(fixed_in)
        return found[0]

    def canonical(self, order=None):
        """The lexicographically greatest optimal solution in the variable `order`.

        This is the sequential fixing procedure of docs/algorithm.md section 5, with the
        exact search in place of the solver. Returns (minimum, solution mask).
        """
        sel = self.search()
        z = sel.bit_count()
        fixed_in = fixed_out = 0
        for v in (order if order is not None else range(len(self.xs))):
            if sel >> v & 1:
                fixed_in |= 1 << v
                continue
            again = self.search(fixed_in | 1 << v, fixed_out, z)
            if again is not None:
                sel = again
                fixed_in |= 1 << v
            else:
                fixed_out |= 1 << v
        return z, sel


# ------------------------------------------------------------ the input rules ----

class SpecError(Exception):
    """An error of docs/algorithm.md section 10 raised by the reference input layer."""

    def __init__(self, kind, message):
        super().__init__(message)
        self.kind = kind
        self.message = message


def invalid(message):
    return SpecError("invalid_input", message)


def solver_error(message):
    return SpecError("solver", message)


TRUE_WORDS = {"true", "t", "yes", "y", "1", "significant"}
FALSE_WORDS = {"false", "f", "no", "n", "0", "not significant", "ns"}


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def coerce_significance(value):
    if isinstance(value, bool):
        return value
    if is_number(value) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        text = value.strip().lower()
        if text in TRUE_WORDS:
            return True
        if text in FALSE_WORDS:
            return False
    raise invalid("cannot coerce significance value to bool: %r" % (value,))


def label_text(value):
    """String conversion of a group label (JSON numbers and strings only)."""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        raise invalid("group labels must be strings or numbers")
    if isinstance(value, float) and value == int(value):
        return str(int(value))
    return str(value)


def check_groups(groups):
    labels = [label_text(g) for g in groups]
    if len(set(labels)) != len(labels):
        raise invalid("group labels must be unique after string conversion")
    if not labels:
        raise invalid("at least one group is required")
    return labels


def match_means(means, groups):
    """Means by group label for `groups` (section 1); None when no means are given."""
    if means is None:
        return None
    table = {}
    for entry in means:
        table[label_text(entry["group"])] = entry.get("mean")
    missing = [g for g in groups if g not in table]
    if missing:
        raise invalid("means are missing values for groups: %r" % (missing,))
    values = []
    for g in groups:
        value = table[g]
        if not is_number(value) or not math.isfinite(value):
            raise invalid("means must be finite numbers")
        values.append(float(value))
    return values


def check_method(options):
    method = options.get("method", "assignment_minimum")
    if method not in ("assignment_minimum", "assignment-minimum"):
        raise invalid("unsupported CLD reduction method: %r" % (method,))


def check_controls(options):
    time_limit = options.get("time_limit")
    if time_limit is not None and (not is_number(time_limit) or not math.isfinite(time_limit)
                                   or time_limit <= 0):
        raise solver_error("time_limit must be positive when provided")
    cap = options.get("max_cliques", DEFAULT_MAX_CLIQUES)
    if cap is not None and (isinstance(cap, bool) or not isinstance(cap, int) or cap < 1):
        raise solver_error("max_cliques must be a positive integer or None")
    return cap


def pairs_to_graph(case):
    """Section 1: rows (and optional means) to (groups, adjacency bit rows, means)."""
    rows = case["input"]["pairs"]
    options = case["options"]
    col1 = options.get("group1", "group1")
    col2 = options.get("group2", "group2")
    cols = options.get("significant", "significant")
    present = set()
    for row in rows:
        present.update(row)
    missing = sorted({col1, col2, cols} - present)
    if missing:
        raise invalid("post_hoc_results missing required columns: %r" % (missing,))
    pairs = []
    for row in rows:
        pairs.append((label_text(row[col1]), label_text(row[col2]),
                      coerce_significance(row[cols])))
    if any(a == b for a, b, _ in pairs):
        raise invalid("post_hoc_results must not contain self-comparisons")
    seen, dup = set(), set()
    for a, b, _ in pairs:
        key = tuple(sorted((a, b)))
        (dup if key in seen else seen).add(key)
    if dup:
        raise invalid("post_hoc_results contains duplicate unordered pairs: %r" % (sorted(dup),))
    means_in = case["input"].get("means")
    if means_in is not None:
        groups = check_groups([entry["group"] for entry in means_in])
    else:
        order = []
        for a, _, _ in pairs:
            if a not in order:
                order.append(a)
        for _, b, _ in pairs:
            if b not in order:
                order.append(b)
        groups = check_groups(order)
    means = match_means(means_in, groups)
    position = {g: i for i, g in enumerate(groups)}
    unknown = sorted({g for a, b, _ in pairs for g in (a, b)} - set(position))
    if unknown:
        raise invalid("post_hoc_results contains groups not present in means/groups: %r"
                      % (unknown,))
    expected_pairs = {(groups[i], groups[j]) if groups[i] <= groups[j] else (groups[j], groups[i])
                      for i in range(len(groups)) for j in range(i + 1, len(groups))}
    if expected_pairs - seen:
        raise invalid("post_hoc_results missing unordered pairwise comparisons: %r"
                      % (sorted(expected_pairs - seen),))
    edges = [(min(position[a], position[b]), max(position[a], position[b]))
             for a, b, significant in pairs if not significant]
    return groups, sorted(edges), means


def adjacency_to_graph(case):
    """Section 2: a matrix (and optional groups and means) to (groups, edges, means)."""
    raw = case["input"]["adjacency"]
    cells = [c for row in raw if isinstance(row, list) for c in row]
    if any(c is None for c in cells):
        raise invalid("adjacency must not contain missing values")
    for c in cells:
        if not (isinstance(c, bool) or (is_number(c) and c in (0, 1))):
            raise invalid("adjacency must contain only booleans or explicit 0/1 values")
    size = len(raw)
    if size == 0 or any(not isinstance(row, list) or len(row) != size for row in raw):
        raise invalid("adjacency must be a square matrix")
    cell = [[bool(c) for c in row] for row in raw]
    if any(cell[i][j] != cell[j][i] for i in range(size) for j in range(size)):
        raise invalid("adjacency must be symmetric")
    if not all(cell[i][i] for i in range(size)):
        raise invalid("adjacency diagonal must be True")
    groups_in = case["input"].get("groups")
    if groups_in is None:
        groups = [str(i + 1) for i in range(size)]
    else:
        groups = check_groups(groups_in)
        if len(groups) != size:
            raise invalid("number of groups must match adjacency dimensions")
    means = match_means(case["input"].get("means"), groups)
    edges = [(i, j) for i in range(size) for j in range(i + 1, size) if cell[i][j]]
    return groups, edges, means


def graph_of(case):
    """Run the input rules for a case; raise SpecError for an error case."""
    if case["call"] == "pairs":
        groups, edges, means = pairs_to_graph(case)
    else:
        groups, edges, means = adjacency_to_graph(case)
    check_method(case["options"])
    cap = check_controls(case["options"])
    return groups, edges, means, cap


# ----------------------------------------------------------------- the result ----

def build_display(model, groups, means, selected, mean_order=None):
    """Sections 7 to 9 for a selected membership mask."""
    n = model.n
    columns = []
    for c, clique in enumerate(model.cliques):
        members = [g for g in clique if selected >> model.index[(c, g)] & 1]
        if members:
            columns.append(members)
    if means is not None:
        def key(members):
            return (-max(means[g] for g in members), min(members))
    else:
        def key(members):
            return (min(members), min(members))
    columns.sort(key=key)  # stable over the canonical clique order
    labels = make_labels(len(columns))
    tokens = [[] for _ in range(n)]
    for label, members in zip(labels, columns):
        for g in members:
            tokens[g].append(label)
    return columns, tokens


def display_text(tokens):
    return "".join(tokens) if all(len(t) == 1 for t in tokens) else " ".join(tokens)


def result_dict(model, groups, means, selected, z):
    """The expected-result object of reduce.json for a selection."""
    n = model.n
    columns, tokens = build_display(model, groups, means, selected)
    after = sum(len(t) for t in tokens)
    before = len(model.xs)
    shares = [[bool(set(tokens[i]) & set(tokens[j])) for j in range(n)] for i in range(n)]
    for i in range(n):
        for j in range(n):
            wanted = i == j or (min(i, j), max(i, j)) in set(model.edges)
            if shares[i][j] != wanted:
                raise AssertionError("display does not preserve the relationships")
    return {
        "groups": list(groups),
        "assignments": {g: tokens[i] for i, g in enumerate(groups)},
        "letters": {g: display_text(tokens[i]) for i, g in enumerate(groups)},
        "stats": {
            "assignments_before": before,
            "assignments_after": after,
            "num_letters_before": len(model.cliques),
            "num_letters_after": len(columns),
            "num_groups": n,
            "num_edges": len(model.edges),
        },
        "solver_status": "Optimal",
        "objective": z,
        "reduction_pct": {"numerator": before - after, "denominator": before},
        "method": "assignment_minimum",
        "relationship_preserved": True,
    }


def solve_case(case, with_alternatives=False):
    """Expected result of a valid case (raises SpecError for an invalid one)."""
    groups, edges, means, cap = graph_of(case)
    model = Model(len(groups), edges)
    if cap is not None and len(model.cliques) > cap:
        raise solver_error("maximal clique enumeration exceeded max_cliques=%d; "
                           "increase max_cliques or pass None to disable the cap" % cap)
    z, selected = model.canonical()
    expected = result_dict(model, groups, means, selected, z)
    if not with_alternatives:
        return expected
    return expected, model, groups, means, selected, z


# ------------------------------------------------------------- input families ----

def graph_record(gid, n, edges, labels=None, means=None, route="adjacency", **extra):
    rec = {"id": gid, "n": n, "edges": [list(e) for e in sorted(edges)],
           "labels": labels, "means": means, "route": route}
    rec.update(extra)
    return rec


def exhaustive_inputs():
    """Every labeled graph with 1 to 5 groups, one file per size."""
    files = {}
    for n in range(1, 6):
        pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
        records = []
        for mask in range(1 << len(pairs)):
            edges = [p for k, p in enumerate(pairs) if mask >> k & 1]
            records.append(graph_record("n%d-%04d" % (n, mask), n, edges))
        files["exhaustive-n%d" % n] = (
            "every labeled graph on %d groups (edge subset number in the id)" % n, records)
    return files


def random_candidates(n):
    records = []
    for j in range(RANDOM_PER_SIZE):
        seed = RANDOM_SEED * 1000 + n * 100 + j
        rng = splitmix64(seed)
        p = 0.25 + 0.6 * j / (RANDOM_PER_SIZE - 1)
        edges = [(a, b) for a in range(n) for b in range(a + 1, n) if next(rng) < p]
        labels = ["T%02d" % (i + 1) for i in range(n)]
        means = None
        if j % 3 != 0:
            means = [{"group": labels[i], "mean": round(next(rng) * 10, 1)} for i in range(n)]
        route = "pairs" if j % 2 == 0 else "adjacency"
        records.append(graph_record(
            "r%02d-%02d" % (n, j), n, edges, labels, means, route,
            seed=seed, p=round(p, 4), row_shuffle=(route == "pairs" and j % 4 == 0),
            means_shuffle=(route == "adjacency" and j % 4 == 1)))
    return records


def random_inputs():
    files, excluded = {}, []
    for n in RANDOM_SIZES:
        kept = []
        for rec in random_candidates(n):
            model = Model(n, [tuple(e) for e in rec["edges"]])
            if len(model.xs) > MAX_RANDOM_VARIABLES:
                excluded.append({
                    "id": rec["id"],
                    "reason": "%d membership variables, more than %d: the pure Python exact "
                              "search is too slow" % (len(model.xs), MAX_RANDOM_VARIABLES)})
            else:
                kept.append(rec)
        files["random-n%02d" % n] = (
            "seeded random graphs on %d groups (splitmix64; seed and edge probability per "
            "graph)" % n, kept)
    return files, excluded


def structured_inputs():
    """Sorted means with a significance threshold: the usual shape of a real CLD."""
    records = []
    for n in (6, 8, 10, 12, 15, 20):
        for threshold in (1.0, 2.0):
            for shuffle in (False, True):
                step = 0.5
                rng = splitmix64(RANDOM_SEED * 7 + n * 10 + int(threshold * 2) + shuffle * 5)
                ranks = shuffled(range(n), rng) if shuffle else list(range(n))
                values = [round(10 - ranks[i] * step, 2) for i in range(n)]
                labels = ["M%02d" % (i + 1) for i in range(n)]
                edges = [(a, b) for a in range(n) for b in range(a + 1, n)
                         if abs(values[a] - values[b]) <= threshold]
                means = [{"group": labels[i], "mean": values[i]} for i in range(n)]
                records.append(graph_record(
                    "s%02d-t%d-%s" % (n, int(threshold), "perm" if shuffle else "sorted"),
                    n, edges, labels, means, "pairs", threshold=threshold))
    return {"structured": ("means 10 down in steps of 0.5, not significant when the means "
                           "differ by at most the threshold; 'perm' lists the groups in a "
                           "shuffled mean order", records)}


def all_input_files():
    files = dict(exhaustive_inputs())
    random_files, excluded = random_inputs()
    files.update(random_files)
    files.update(structured_inputs())
    return files, excluded


def input_text(name, source, records):
    header = {"schema_version": SCHEMA_VERSION, "name": name, "source": source}
    return dump_records(header, "graphs", records)


# --------------------------------------------------------------- the fixtures ----

def pairs_rows(labels, edges, rng=None, flip=False):
    """Pairwise rows for a graph on `labels`; shuffled and flipped when a rng is given."""
    nonsig = {tuple(e) for e in edges}
    rows = []
    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            rows.append([labels[i], labels[j], (i, j) not in nonsig])
    if rng is not None:
        rows = shuffled(rows, rng)
        if flip:
            rows = [[b, a, s] if next(rng) < 0.5 else [a, b, s] for a, b, s in rows]
    return [{"group1": a, "group2": b, "significant": s} for a, b, s in rows]


def case_from_record(rec):
    n = rec["n"]
    labels = rec["labels"]
    means = rec["means"]
    if rec["route"] == "pairs":
        rng = splitmix64(rec["seed"] + 17) if rec.get("row_shuffle") else None
        rows = pairs_rows(labels, rec["edges"], rng, flip=True)
        return {"id": rec["id"], "call": "pairs",
                "input": {"pairs": rows, "means": means}, "options": {}}
    matrix = [[1 if i == j or [min(i, j), max(i, j)] in rec["edges"] else 0
               for j in range(n)] for i in range(n)]
    entry = means
    if means is not None and rec.get("means_shuffle"):
        entry = shuffled(means, splitmix64(rec["seed"] + 29))
    return {"id": rec["id"], "call": "adjacency",
            "input": {"adjacency": matrix, "groups": labels, "means": entry}, "options": {}}


def exhaustive_case(rec):
    n = rec["n"]
    edge_set = {tuple(e) for e in rec["edges"]}
    matrix = [[1 if i == j or (min(i, j), max(i, j)) in edge_set else 0 for j in range(n)]
              for i in range(n)]
    return {"id": rec["id"], "call": "adjacency",
            "input": {"adjacency": matrix, "groups": None, "means": None}, "options": {}}


def read_csv_rows(name):
    text = read_text(DATA / name)
    return list(csv.DictReader(io.StringIO(text, newline="")))


def data_pairs(name):
    rows = []
    for r in read_csv_rows(name):
        rows.append({"group1": r["group1"], "group2": r["group2"],
                     "significant": coerce_significance(r["significant"])})
    return rows


def data_means(name):
    return [{"group": r["group"], "mean": float(r["mean"])} for r in read_csv_rows(name)]


def adjacency_rows(n, edges):
    nonsig = {tuple(e) for e in edges}
    return [[1 if i == j or (min(i, j), max(i, j)) in nonsig else 0 for j in range(n)]
            for i in range(n)]


def hand_cases():
    """Hand-built valid cases. Returns a list of cases (ids start with 'hand/')."""
    cases = []

    def add(cid, call, inputs, options=None):
        cases.append({"id": "hand/" + cid, "call": call, "input": inputs,
                      "options": options or {}})

    abc_pairs = data_pairs("simple_abc_to_ac_pairs.csv")
    abc_means = data_means("simple_abc_to_ac_means.csv")
    add("simple-abc-pairs-means", "pairs", {"pairs": abc_pairs, "means": abc_means})
    add("simple-abc-pairs-no-means", "pairs", {"pairs": abc_pairs, "means": None})
    add("simple-abc-adjacency", "adjacency",
        {"adjacency": adjacency_rows(5, [(0, 1), (0, 2), (1, 2), (1, 3), (2, 3), (2, 4), (3, 4)]),
         "groups": None, "means": abc_means})
    add("wheat", "pairs", {"pairs": data_pairs("piepho2004_wheat_pairs.csv"), "means": None})
    # D4: one optimum, but the canonical clique order renames group 3 from A to C.
    add("canonical-order-rename", "adjacency",
        {"adjacency": adjacency_rows(5, [(0, 1), (0, 2), (0, 3), (0, 4), (1, 4), (2, 4)]),
         "groups": ["0", "1", "2", "3", "4"], "means": None})
    # A star: 27 cliques of two groups, so the center gets labels past Z.
    star = [(0, i) for i in range(1, 28)]
    add("star-28", "adjacency",
        {"adjacency": adjacency_rows(28, star),
         "groups": ["center"] + ["leaf_%d" % i for i in range(1, 28)], "means": None})
    add("complete-6", "adjacency",
        {"adjacency": adjacency_rows(6, [(i, j) for i in range(6) for j in range(i + 1, 6)]),
         "groups": ["a", "b", "c", "d", "e", "f"], "means": None})
    add("empty-5", "adjacency",
        {"adjacency": adjacency_rows(5, []), "groups": None, "means": None})
    add("single-group", "adjacency",
        {"adjacency": [[1]], "groups": ["solo"], "means": [{"group": "solo", "mean": 2.5}]})
    add("two-groups-different", "pairs",
        {"pairs": [{"group1": "x", "group2": "y", "significant": True}], "means": None})
    add("two-groups-same", "pairs",
        {"pairs": [{"group1": "x", "group2": "y", "significant": False}], "means": None})
    add("path-6", "adjacency",
        {"adjacency": adjacency_rows(6, [(i, i + 1) for i in range(5)]),
         "groups": None, "means": None})
    add("cycle-5", "adjacency",
        {"adjacency": adjacency_rows(5, [(i, (i + 1) % 5) for i in range(5)]),
         "groups": None, "means": None})
    add("two-triangles-shared-edge", "adjacency",
        {"adjacency": adjacency_rows(4, [(0, 1), (0, 2), (1, 2), (1, 3), (2, 3)]),
         "groups": None, "means": None})
    add("disconnected-triangle-pair-isolated", "adjacency",
        {"adjacency": adjacency_rows(6, [(0, 1), (0, 2), (1, 2), (3, 4)]),
         "groups": None, "means": None})
    # max_cliques: a cap equal to the clique count passes; null removes the cap.
    ident = adjacency_rows(3, [])
    add("max-cliques-equal-to-count", "adjacency",
        {"adjacency": ident, "groups": None, "means": None}, {"max_cliques": 3})
    add("max-cliques-null", "adjacency",
        {"adjacency": adjacency_rows(5, []), "groups": None, "means": None},
        {"max_cliques": None})
    add("max-cliques-explicit-default", "adjacency",
        {"adjacency": ident, "groups": None, "means": None}, {"max_cliques": 10000})
    add("method-hyphen", "adjacency",
        {"adjacency": ident, "groups": None, "means": None},
        {"method": "assignment-minimum"})
    # Significance forms (section 1).
    forms = [True, False, "yes", "No", " NS ", "significant", "T", 1, 0,
             "not significant", "y", "f", "1", "0", "TRUE", "False"]
    labels = ["g%d" % i for i in range(1, 7)]
    pairs = [(i, j) for i in range(6) for j in range(i + 1, 6)]
    rows = [{"group1": labels[i], "group2": labels[j], "significant": forms[k % len(forms)]}
            for k, (i, j) in enumerate(pairs)]
    add("significance-forms", "pairs", {"pairs": rows, "means": None})
    # Column names, extra columns, and numeric labels.
    add("custom-column-names", "pairs",
        {"pairs": [{"a": "u", "b": "v", "sig": 0, "note": "x"},
                   {"a": "u", "b": "w", "sig": 1, "note": "y"},
                   {"a": "v", "b": "w", "sig": 0, "note": "z"}], "means": None},
        {"group1": "a", "group2": "b", "significant": "sig"})
    add("extra-columns-ignored", "pairs",
        {"pairs": [{"group1": "u", "group2": "v", "significant": False, "p": 0.2},
                   {"group1": "u", "group2": "w", "significant": True, "p": 0.001},
                   {"group1": "v", "group2": "w", "significant": False, "p": 0.3}],
         "means": None})
    add("numeric-labels", "pairs",
        {"pairs": [{"group1": 10, "group2": 2, "significant": False},
                   {"group1": 10, "group2": 3, "significant": True},
                   {"group1": 2, "group2": 3, "significant": False}], "means": None})
    # Group order: first appearance in group1, then in group2.
    add("appearance-order", "pairs",
        {"pairs": [{"group1": "b", "group2": "a", "significant": False},
                   {"group1": "c", "group2": "a", "significant": True},
                   {"group1": "c", "group2": "b", "significant": False}], "means": None})
    # Means: order of the means is the group order; ties; negatives; mean order differs
    # from label order.
    tri = [{"group1": "p", "group2": "q", "significant": False},
           {"group1": "p", "group2": "r", "significant": True},
           {"group1": "q", "group2": "r", "significant": False}]
    add("means-order-is-group-order", "pairs",
        {"pairs": tri, "means": [{"group": "r", "mean": 1.0}, {"group": "q", "mean": 2.0},
                                 {"group": "p", "mean": 3.0}]})
    add("means-ties", "pairs",
        {"pairs": tri, "means": [{"group": "p", "mean": 2.0}, {"group": "q", "mean": 2.0},
                                 {"group": "r", "mean": 2.0}]})
    add("means-negative-and-large", "pairs",
        {"pairs": tri, "means": [{"group": "p", "mean": -1500.25}, {"group": "q", "mean": 3.5e6},
                                 {"group": "r", "mean": -0.0}]})
    add("adjacency-means-matched-by-label", "adjacency",
        {"adjacency": adjacency_rows(4, [(0, 1), (1, 2), (2, 3)]),
         "groups": ["w", "x", "y", "z"],
         "means": [{"group": "z", "mean": 9.0}, {"group": "x", "mean": 1.0},
                   {"group": "w", "mean": 5.0}, {"group": "y", "mean": 7.0}]})
    add("adjacency-booleans", "adjacency",
        {"adjacency": [[True, False, True], [False, True, False], [True, False, True]],
         "groups": ["a", "b", "c"], "means": None})
    return cases


def labels_cases():
    return [{"id": "count-%d" % c, "count": c, "labels": make_labels(c)} for c in LABEL_COUNTS]


def error_case(cid, call, inputs, kind, prefix, options=None):
    return {"id": "error/" + cid, "call": call, "input": inputs, "options": options or {},
            "expected": {"kind": kind, "message_prefix": prefix}}


def error_cases():
    inv, sol = "invalid_input", "solver"
    abc = {"group1": "a", "group2": "b", "significant": False}
    ac = {"group1": "a", "group2": "c", "significant": True}
    bc = {"group1": "b", "group2": "c", "significant": False}
    triple = [abc, ac, bc]
    ident2 = [[1, 0], [0, 1]]
    cases = []

    def pairs(cid, rows, prefix, means=None, options=None):
        cases.append(error_case(cid, "pairs", {"pairs": rows, "means": means}, inv, prefix,
                                options))

    def adj(cid, matrix, prefix, groups=None, means=None, options=None, kind=inv):
        cases.append(error_case(cid, "adjacency",
                                {"adjacency": matrix, "groups": groups, "means": means}, kind,
                                prefix, options))

    pre_cols = "post_hoc_results missing required columns: "
    pairs("pairs-missing-significant-column", [{"group1": "a", "group2": "b"}], pre_cols)
    pairs("pairs-missing-column-for-custom-name", triple, pre_cols,
          options={"group1": "g1"})
    pre_coerce = "cannot coerce significance value to bool: "
    for name, value in (("word", "maybe"), ("null", None), ("number-2", 2),
                        ("number-half", 0.5), ("empty-string", "")):
        pairs("pairs-significance-" + name,
              [dict(abc, significant=value), ac, bc], pre_coerce)
    pairs("pairs-self-comparison", [dict(abc, group2="a"), ac, bc],
          "post_hoc_results must not contain self-comparisons")
    pre_dup = "post_hoc_results contains duplicate unordered pairs: "
    pairs("pairs-duplicate-reversed", triple + [dict(abc, group1="b", group2="a")], pre_dup)
    pairs("pairs-duplicate-same-order", triple + [abc], pre_dup)
    pairs("pairs-unknown-group-with-means", triple,
          "post_hoc_results contains groups not present in means/groups: ",
          means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": 2.0}])
    pairs("pairs-missing-pair", [abc, ac],
          "post_hoc_results missing unordered pairwise comparisons: ")
    pairs("pairs-duplicate-group-in-means", triple, "group labels must be unique after string "
          "conversion", means=[{"group": "a", "mean": 1.0}, {"group": "a", "mean": 2.0},
                               {"group": "b", "mean": 3.0}, {"group": "c", "mean": 4.0}])
    pairs("pairs-mean-null", triple, "means must be finite numbers",
          means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": None},
                 {"group": "c", "mean": 3.0}])
    pairs("pairs-mean-string", triple, "means must be finite numbers",
          means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": "high"},
                 {"group": "c", "mean": 3.0}])
    # Order of the checks (section 1): coercion, self comparison, duplicates, unknown groups,
    # missing pairs.
    pairs("order-coercion-before-self-comparison",
          [{"group1": "a", "group2": "a", "significant": "maybe"}, ac, bc], pre_coerce)
    pairs("order-self-comparison-before-duplicate",
          triple + [abc, dict(abc, group2="a")],
          "post_hoc_results must not contain self-comparisons")
    pairs("order-duplicate-before-unknown-group", triple + [abc], pre_dup,
          means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": 2.0}])
    pairs("order-unknown-group-before-missing-pair", [abc, ac],
          "post_hoc_results contains groups not present in means/groups: ",
          means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": 2.0}])
    pairs("order-input-before-method", [abc, ac], "post_hoc_results missing unordered pairwise "
          "comparisons: ", options={"method": "greedy"})
    # Adjacency input (section 2).
    adj("adjacency-missing-value", [[1, None], [None, 1]],
        "adjacency must not contain missing values")
    adj("adjacency-string-values", [["True", "False"], ["False", "True"]],
        "adjacency must contain only booleans or explicit 0/1 values")
    adj("adjacency-number-2", [[1, 2], [2, 1]],
        "adjacency must contain only booleans or explicit 0/1 values")
    adj("adjacency-number-half", [[1, 0.5], [0.5, 1]],
        "adjacency must contain only booleans or explicit 0/1 values")
    adj("adjacency-not-square", [[1, 0, 0], [0, 1, 0]], "adjacency must be a square matrix")
    adj("adjacency-empty-list", [], "adjacency must be a square matrix")
    adj("adjacency-asymmetric", [[1, 1], [0, 1]], "adjacency must be symmetric")
    adj("adjacency-diagonal-false", [[1, 0, 0], [0, 0, 0], [0, 0, 1]],
        "adjacency diagonal must be ")
    adj("adjacency-groups-count", ident2, "number of groups must match adjacency dimensions",
        groups=["a", "b", "c"])
    adj("adjacency-groups-duplicate", ident2,
        "group labels must be unique after string conversion", groups=["a", "a"])
    adj("adjacency-groups-duplicate-after-conversion", ident2,
        "group labels must be unique after string conversion", groups=[1, "1"])
    adj("adjacency-groups-empty", [[1]], "at least one group is required", groups=[])
    adj("adjacency-means-missing-group", ident2, "means are missing values for groups: ",
        groups=["a", "b"], means=[{"group": "a", "mean": 1.0}])
    adj("adjacency-mean-null", ident2, "means must be finite numbers", groups=["a", "b"],
        means=[{"group": "a", "mean": 1.0}, {"group": "b", "mean": None}])
    adj("adjacency-mean-string", ident2, "means must be finite numbers", groups=["a", "b"],
        means=[{"group": "a", "mean": "1"}, {"group": "b", "mean": 2.0}])
    adj("order-values-before-shape", [[1, 2, 3], [1, 1, 1]],
        "adjacency must contain only booleans or explicit 0/1 values")
    adj("order-missing-before-values", [[1, None], ["x", 1]],
        "adjacency must not contain missing values")
    adj("order-shape-before-symmetry", [[1, 0, 1], [0, 1, 0]], "adjacency must be a square matrix")
    adj("order-symmetry-before-diagonal", [[0, 1], [0, 1]], "adjacency must be symmetric")
    adj("order-diagonal-before-groups", [[1, 0], [0, 0]], "adjacency diagonal must be ",
        groups=["a"])
    adj("order-groups-before-means", ident2, "number of groups must match adjacency dimensions",
        groups=["a"], means=[{"group": "z", "mean": 1.0}])
    # Method and solver controls (sections 2 and 6).
    pre_method = "unsupported CLD reduction method: "
    adj("method-unsupported", ident2, pre_method, options={"method": "greedy"})
    adj("method-before-time-limit", ident2, pre_method,
        options={"method": "greedy", "time_limit": 0})
    adj("adjacency-before-method", [[1, 0], [1, 1]], "adjacency must be symmetric",
        options={"method": "greedy"})
    pre_time = "time_limit must be positive when provided"
    for name, value in (("zero", 0), ("negative", -1), ("string", "30"), ("boolean", True)):
        adj("time-limit-" + name, ident2, pre_time, options={"time_limit": value}, kind=sol)
    pre_cap = "max_cliques must be a positive integer or "
    for name, value in (("zero", 0), ("negative", -3), ("fraction", 1.5), ("string", "10"),
                        ("boolean", True)):
        adj("max-cliques-" + name, ident2, pre_cap, options={"max_cliques": value}, kind=sol)
    adj("time-limit-before-max-cliques", ident2, pre_time,
        options={"time_limit": 0, "max_cliques": 0}, kind=sol)
    adj("max-cliques-exceeded", adjacency_rows(3, []),
        "maximal clique enumeration exceeded max_cliques=", options={"max_cliques": 2}, kind=sol)
    adj("max-cliques-exceeded-by-one", adjacency_rows(5, [(0, 1)]),
        "maximal clique enumeration exceeded max_cliques=", options={"max_cliques": 3},
        kind=sol)
    return cases


def checker_fixture(wheat_expected, model, groups, means, selected, z):
    """Wrong results for the wheat case that every runner's checker must reject."""
    n = model.n
    # (1) A display that loses a relationship: drop a token that the only shared letter of
    # some non-significant pair depends on.
    columns, tokens = build_display(model, groups, means, selected)
    broken = None
    for g in range(n):
        for token in tokens[g]:
            trial = [list(t) for t in tokens]
            trial[g] = [t for t in trial[g] if t != token]
            if not trial[g]:
                continue
            if any(not set(trial[i]) & set(trial[j]) for i, j in model.edges):
                broken = trial
                break
        if broken:
            break
    assert broken is not None
    lost = dict(wheat_expected)
    lost["assignments"] = {g: broken[i] for i, g in enumerate(groups)}
    lost["letters"] = {g: display_text(broken[i]) for i, g in enumerate(groups)}
    lost["stats"] = dict(wheat_expected["stats"],
                         assignments_after=sum(len(t) for t in broken))
    # (2) A display that is valid but not minimal: the maximal covering.
    full = (1 << len(model.xs)) - 1
    _, full_tokens = build_display(model, groups, means, full)
    maximal = dict(wheat_expected)
    maximal["assignments"] = {g: full_tokens[i] for i, g in enumerate(groups)}
    maximal["letters"] = {g: display_text(full_tokens[i]) for i, g in enumerate(groups)}
    maximal["stats"] = dict(wheat_expected["stats"],
                            assignments_after=len(model.xs),
                            num_letters_after=len(model.cliques))
    maximal["objective"] = len(model.xs)
    maximal["reduction_pct"] = {"numerator": 0, "denominator": len(model.xs)}
    return {"schema_version": SCHEMA_VERSION, "kind": "checker", "case": "hand/wheat",
            "bad": [{"name": "loses_relationship", "result": lost},
                    {"name": "not_minimal", "result": maximal}]}


def non_canonical_wheat(model, groups, means, canonical_mask, z, wheat_expected):
    """A valid optimum that is not the canonical one: the canonical solve in reverse order."""
    _, other = model.canonical(order=list(reversed(range(len(model.xs)))))
    assert other != canonical_mask and other.bit_count() == z
    result = result_dict(model, groups, means, other, z)
    assert result["assignments"] != wheat_expected["assignments"]
    return result


def build(files, excluded):
    """All outputs as {relative path: text}, plus the manifest object."""
    outputs = {}
    manifest_inputs = {}
    for name, (source, records) in sorted(files.items()):
        text = input_text(name, source, records)
        outputs["inputs/%s.json" % name] = text
        manifest_inputs[name] = {"sha256": sha256(text), "graphs": len(records),
                                 "origin": "generate.py", "source": source}

    cases = []
    for name, (_, records) in sorted(files.items()):
        for rec in records:
            cases.append(exhaustive_case(rec) if name.startswith("exhaustive")
                         else case_from_record(rec))
    cases.extend(hand_cases())
    reduce_cases = []
    wheat = None
    for case in cases:
        if case["id"] == "hand/wheat":
            expected, model, groups, means, selected, z = solve_case(case, True)
            expected_wheat = expected
            alt = non_canonical_wheat(model, groups, means, selected, z, expected)
            wheat = (expected, model, groups, means, selected, z)
            case["expected"] = expected
            case["non_canonical"] = alt
        else:
            case["expected"] = solve_case(case)
        reduce_cases.append(case)
    checker = checker_fixture(*wheat)
    errors = error_cases()
    for case in errors:
        try:
            solve_case(case)
        except SpecError as err:
            want = case["expected"]
            if err.kind != want["kind"] or not err.message.startswith(want["message_prefix"]):
                raise AssertionError("%s: reference raised %s %r" % (case["id"], err.kind,
                                                                    err.message))
        else:
            raise AssertionError("%s: reference accepted the input" % case["id"])
    labels = labels_cases()

    fixtures = {
        "reduce.json": dump_records({"schema_version": SCHEMA_VERSION, "kind": "reduce"},
                                    "cases", reduce_cases),
        "errors.json": dump_records({"schema_version": SCHEMA_VERSION, "kind": "errors"},
                                    "cases", errors),
        "labels.json": dump_records({"schema_version": SCHEMA_VERSION, "kind": "labels"},
                                    "cases", labels),
        "checker.json": dump(checker),
    }
    for fname, text in fixtures.items():
        outputs["fixtures/" + fname] = text

    counts = {
        "reduce": len(reduce_cases),
        "reduce_exhaustive_1_to_5_groups": sum(1 for c in reduce_cases
                                               if c["id"].startswith("n")),
        "reduce_random_6_to_12_groups": sum(1 for c in reduce_cases if c["id"].startswith("r")),
        "reduce_structured": sum(1 for c in reduce_cases if c["id"].startswith("s")),
        "reduce_hand": sum(1 for c in reduce_cases if c["id"].startswith("hand/")),
        "errors": len(errors),
        "labels": len(labels),
        "checker_bad_results": len(checker["bad"]) + 1,
    }
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "data": {name: {"sha256": sha256(read_text(DATA / name))} for name in DATA_FILES},
        "inputs": manifest_inputs,
        "counts": counts,
        "excluded": excluded + [{
            "id": "exhaustive graphs with 6 or more groups",
            "reason": "2^15 graphs on 6 groups and 2^21 on 7 are too many fixtures; "
                      "test_generate.py checks the search against plain enumeration on all "
                      "graphs with up to 6 groups"}],
    }
    outputs["manifest.json"] = dump(manifest)
    return outputs, manifest


# ----------------------------------------------------------------------- main ----

def write_text(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def generated_names():
    return sorted([p.relative_to(ROOT).as_posix() for p in INPUTS.glob("*.json")]
                  + [p.relative_to(ROOT).as_posix() for p in FIXTURES.glob("*.json")]
                  + (["manifest.json"] if MANIFEST.exists() else []))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = ap.parse_args(argv)

    problems = []
    for name in DATA_FILES:
        original = DATA / name
        copy = PY_EXAMPLES / name
        if not original.exists():
            problems.append("missing data file conformance/data/%s" % name)
        elif not copy.exists():
            problems.append("missing copy python/examples/%s" % name)
        elif read_text(original) != read_text(copy):
            problems.append("python/examples/%s differs from conformance/data/%s" % (name, name))
    if problems:
        print("\n".join(problems))
        return 1

    files, excluded = all_input_files()
    outputs, manifest = build(files, excluded)
    summary = ", ".join("%s: %d" % kv for kv in manifest["counts"].items())

    if args.write:
        for rel, text in outputs.items():
            write_text(ROOT / rel, text)
        for rel in generated_names():
            if rel not in outputs:
                (ROOT / rel).unlink()
                print("removed %s" % rel)
        print("wrote %s" % summary)
        return 0

    for rel, text in sorted(outputs.items()):
        path = ROOT / rel
        if not path.exists():
            problems.append("missing %s" % rel)
        elif read_text(path) != text:
            problems.append("%s differs" % rel)
    for rel in generated_names():
        if rel not in outputs:
            problems.append("unexpected file %s" % rel)
    if problems:
        print("\n".join(problems))
        return 1
    print("conformance files are current: %s" % summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
