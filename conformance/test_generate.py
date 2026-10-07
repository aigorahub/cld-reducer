#!/usr/bin/env python3
"""Hand-checked tests for conformance/generate.py. Standard library only.

    python3 conformance/test_generate.py

The main test compares the generator's exact search with plain enumeration of every
membership subset on every labeled graph with up to 6 groups.
"""

import ast
import itertools
import json
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate as g  # noqa: E402

HERE = Path(__file__).resolve().parent


# ----------------------------------------------------- plain enumeration oracle ----

def brute_force_cliques(n, edges):
    """Maximal cliques by testing every vertex subset (independent of generate.py)."""
    nonsig = {tuple(e) for e in edges}

    def is_clique(s):
        return all((a, b) in nonsig for a, b in itertools.combinations(s, 2))

    cliques = [s for r in range(1, n + 1) for s in itertools.combinations(range(n), r)
               if is_clique(s)]
    return sorted(c for c in cliques if not any(set(c) < set(d) for d in cliques))


def plain_optimum(n, edges, cliques):
    """Minimum and lexicographically greatest optimal selection by enumerating subsets.

    Every subset of the optional memberships is tried (a membership is forced when the
    maximal covering without it fails; every feasible selection contains the forced
    ones). Coverage of a clique's subset is tabulated, then tables are combined over
    all products. Returns (minimum, set of (clique, group) of the greatest optimum,
    number of optimal selections).
    """
    requirements = list(edges) + list(range(n))   # edges first, then one per group
    bit = {r if isinstance(r, tuple) else ("g", r): k for k, r in enumerate(requirements)}
    full = (1 << len(requirements)) - 1

    def coverage(chosen):
        mask = 0
        for a, b in itertools.combinations(sorted(chosen), 2):
            if (a, b) in bit:
                mask |= 1 << bit[(a, b)]
        for member in chosen:
            mask |= 1 << bit[("g", member)]
        return mask

    chosen_all = [set(c) for c in cliques]

    def union_without(skip):
        mask = 0
        for c, members in enumerate(chosen_all):
            use = members - {skip[1]} if skip and skip[0] == c else members
            mask |= coverage(use)
        return mask

    forced = {(c, m) for c, members in enumerate(cliques) for m in members
              if union_without((c, m)) != full}
    optional = [[m for m in members if (c, m) not in forced]
                for c, members in enumerate(cliques)]
    forced_by_clique = [{m for m in members if (c, m) in forced}
                        for c, members in enumerate(cliques)]

    # Per clique: every subset of its optional members; first optional member is the MSB.
    tables = []
    for c, opt in enumerate(optional):
        rows = []
        for code in range(1 << len(opt)):
            pick = {opt[k] for k in range(len(opt)) if code >> (len(opt) - 1 - k) & 1}
            rows.append((code, coverage(forced_by_clique[c] | pick), len(pick)))
        tables.append(rows)

    # Chunks of consecutive cliques with at most 12 optional bits each.
    chunks, current, bits = [], [], 0
    for c, opt in enumerate(optional):
        if current and bits + len(opt) > 12:
            chunks.append(current)
            current, bits = [], 0
        current.append(c)
        bits += len(opt)
    chunks.append(current)
    chunk_rows = []
    for members in chunks:
        rows = []
        for combo in itertools.product(*(tables[c] for c in members)):
            cov = 0
            pc = 0
            codes = []
            for code, c_cov, c_pc in combo:
                cov |= c_cov
                pc += c_pc
                codes.append(code)
            rows.append((tuple(codes), cov, pc))
        chunk_rows.append(rows)

    base_cost = len(forced)
    forced_cov = 0
    for c in range(len(cliques)):
        forced_cov |= coverage(forced_by_clique[c])
    best_cost, best_key, count = None, None, 0
    *head, last = chunk_rows
    last_cov = [r[1] for r in last]
    min_last = min(r[2] for r in last)
    for combo in itertools.product(*head):
        cov = forced_cov
        pc = 0
        for _, c_cov, c_pc in combo:
            cov |= c_cov
            pc += c_pc
        if best_cost is not None and base_cost + pc + min_last > best_cost:
            continue
        need = full & ~cov
        for i in [i for i, c_cov in enumerate(last_cov) if c_cov & need == need]:
            cost = base_cost + pc + last[i][2]
            key = tuple(r[0] for r in combo) + (last[i][0],)
            if best_cost is None or cost < best_cost:
                best_cost, best_key, count = cost, key, 1
            elif cost == best_cost:
                best_key, count = key, count + 1
    selected = set()
    flat = [code for part in best_key for code in part]
    for c, opt in enumerate(optional):
        code = flat[c]
        for k, member in enumerate(opt):
            if code >> (len(opt) - 1 - k) & 1:
                selected.add((c, member))
        selected |= {(c, m) for m in forced_by_clique[c]}
    return best_cost, selected, count


def all_graphs(n):
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    for mask in range(1 << len(pairs)):
        yield [p for k, p in enumerate(pairs) if mask >> k & 1]


def selection_set(model, mask):
    return {model.xs[k] for k in range(len(model.xs)) if mask >> k & 1}


# --------------------------------------------------------------------- tests ----

class SplitmixTest(unittest.TestCase):
    def test_known_first_value(self):
        # splitmix64 with seed 0 starts with 0xE220A8397B1DCDAF.
        self.assertEqual(next(g.splitmix64(0)), 0xE220A8397B1DCDAF / 2.0 ** 64)

    def test_shuffle_is_a_permutation_and_deterministic(self):
        a = g.shuffled(range(10), g.splitmix64(5))
        self.assertEqual(sorted(a), list(range(10)))
        self.assertEqual(a, g.shuffled(range(10), g.splitmix64(5)))


class LabelTest(unittest.TestCase):
    def test_labels(self):
        labels = g.make_labels(704)
        self.assertEqual(labels[:3], ["A", "B", "C"])
        self.assertEqual(labels[25:29], ["Z", "AA", "AB", "AC"])
        self.assertEqual(labels[51:53], ["AZ", "BA"])
        self.assertEqual(labels[701:704], ["ZZ", "AAA", "AAB"])
        self.assertEqual(g.make_labels(0), [])
        self.assertEqual(len(set(labels)), 704)


class CliqueTest(unittest.TestCase):
    def test_against_brute_force_on_every_graph_up_to_6_groups(self):
        for n in range(1, 7):
            for edges in all_graphs(n):
                model = g.Model(n, edges)
                self.assertEqual(model.cliques, brute_force_cliques(n, edges),
                                 "n=%d edges=%s" % (n, edges))

    def test_canonical_order_of_the_d4_example(self):
        model = g.Model(5, [(0, 1), (0, 2), (0, 3), (0, 4), (1, 4), (2, 4)])
        self.assertEqual(model.cliques, [(0, 1, 4), (0, 2, 4), (0, 3)])

    def test_isolated_group_is_a_singleton_clique(self):
        self.assertEqual(g.Model(3, [(0, 1)]).cliques, [(0, 1), (2,)])


class HandCheckedTest(unittest.TestCase):
    def solve(self, call, inputs, options=None):
        case = {"id": "t", "call": call, "input": inputs, "options": options or {}}
        return g.solve_case(case)

    def test_simple_abc_display(self):
        means = g.data_means("simple_abc_to_ac_means.csv")
        pairs = g.data_pairs("simple_abc_to_ac_pairs.csv")
        out = self.solve("pairs", {"pairs": pairs, "means": means})
        self.assertEqual(out["letters"],
                         {"1": "A", "2": "AB", "3": "AC", "4": "BC", "5": "C"})
        self.assertEqual(out["stats"]["assignments_before"], 9)
        self.assertEqual(out["stats"]["assignments_after"], 8)

    def test_d4_example_renames_group_3(self):
        edges = [(0, 1), (0, 2), (0, 3), (0, 4), (1, 4), (2, 4)]
        out = self.solve("adjacency", {"adjacency": g.adjacency_rows(5, edges),
                                        "groups": None, "means": None})
        # Cliques {0,1,4}, {0,2,4}, {0,3} all start at group 0, so they keep this order.
        self.assertEqual(out["letters"], {"1": "ABC", "2": "A", "3": "B", "4": "C", "5": "AB"})
        self.assertEqual(out["stats"]["assignments_before"], out["stats"]["assignments_after"])

    def test_means_decide_letter_order(self):
        # Path 0-1-2: cliques {0,1} and {1,2}; the clique with the larger highest mean first.
        adj = g.adjacency_rows(3, [(0, 1), (1, 2)])
        low_first = self.solve("adjacency", {"adjacency": adj, "groups": ["a", "b", "c"],
                                             "means": [{"group": "a", "mean": 1.0},
                                                       {"group": "b", "mean": 2.0},
                                                       {"group": "c", "mean": 5.0}]})
        self.assertEqual(low_first["letters"], {"a": "B", "b": "AB", "c": "A"})
        no_means = self.solve("adjacency", {"adjacency": adj, "groups": ["a", "b", "c"],
                                            "means": None})
        self.assertEqual(no_means["letters"], {"a": "A", "b": "AB", "c": "B"})

    def test_star_with_28_groups_uses_labels_after_z(self):
        star = [(0, i) for i in range(1, 28)]
        out = self.solve("adjacency", {"adjacency": g.adjacency_rows(28, star),
                                         "groups": None, "means": None})
        tokens = out["assignments"]["1"]
        self.assertEqual(len(tokens), 27)
        self.assertEqual(tokens[-2:], ["Z", "AA"])
        self.assertIn(" ", out["letters"]["1"])
        self.assertEqual(out["letters"]["1"].split(), tokens)

    def test_complete_and_empty_graph(self):
        n = 5
        full = self.solve("adjacency", {"adjacency": g.adjacency_rows(
            n, [(i, j) for i in range(n) for j in range(i + 1, n)]),
            "groups": None, "means": None})
        self.assertEqual(set(full["letters"].values()), {"A"})
        empty = self.solve("adjacency", {"adjacency": g.adjacency_rows(n, []),
                                          "groups": None, "means": None})
        self.assertEqual(list(empty["letters"].values()), ["A", "B", "C", "D", "E"])

    def test_reduction_pct_parts(self):
        out = self.solve("adjacency", {"adjacency": g.adjacency_rows(
            5, [(0, 1), (0, 2), (1, 2), (1, 3), (2, 3), (2, 4), (3, 4)]),
            "groups": None, "means": None})
        self.assertEqual(out["reduction_pct"], {"numerator": 1, "denominator": 9})

    def test_max_cliques_cap(self):
        ident = {"adjacency": g.adjacency_rows(3, []), "groups": None, "means": None}
        self.solve("adjacency", ident, {"max_cliques": 3})
        with self.assertRaises(g.SpecError) as ctx:
            self.solve("adjacency", ident, {"max_cliques": 2})
        self.assertEqual(ctx.exception.kind, "solver")


class WheatTest(unittest.TestCase):
    def test_wheat_counts_and_64_optimal_coverings(self):
        pairs = g.data_pairs("piepho2004_wheat_pairs.csv")
        self.assertEqual(len(pairs), 190)
        case = {"id": "t", "call": "pairs", "input": {"pairs": pairs, "means": None},
                "options": {}}
        expected, model, groups, means, selected, z = g.solve_case(case, True)
        self.assertEqual(len(model.cliques), 4)
        self.assertEqual(len(model.xs), 56)
        self.assertEqual(z, 44)
        self.assertEqual(expected["stats"]["num_letters_after"], 4)
        plain_z, plain_sel, count = plain_optimum(model.n, model.edges, model.cliques)
        self.assertEqual(plain_z, 44)
        self.assertEqual(count, 64)
        self.assertEqual(plain_sel, selection_set(model, selected))
        # The fixture and the checker data agree with this result.
        fixture = json.loads((HERE / "fixtures" / "reduce.json").read_text(encoding="utf-8"))
        wheat = next(c for c in fixture["cases"] if c["id"] == "hand/wheat")
        self.assertEqual(wheat["expected"], expected)
        self.assertNotEqual(wheat["non_canonical"]["assignments"], expected["assignments"])
        self.assertEqual(wheat["non_canonical"]["stats"]["assignments_after"], 44)


class SearchAgainstEnumerationTest(unittest.TestCase):
    def check(self, n, edges):
        model = g.Model(n, edges)
        z, mask = model.canonical()
        plain_z, plain_sel, _ = plain_optimum(n, model.edges, model.cliques)
        self.assertEqual(z, plain_z, "n=%d edges=%s" % (n, edges))
        self.assertEqual(selection_set(model, mask), plain_sel, "n=%d edges=%s" % (n, edges))
        self.assertEqual(model.search().bit_count(), plain_z)

    def test_every_graph_with_up_to_6_groups(self):
        total = 0
        for n in range(1, 7):
            for edges in all_graphs(n):
                self.check(n, edges)
                total += 1
        self.assertEqual(total, 1 + 2 + 8 + 64 + 1024 + 32768)


class InputRuleTest(unittest.TestCase):
    def test_significance_forms(self):
        for value in (True, "true", "T", " Yes ", "y", "1", "significant", 1):
            self.assertTrue(g.coerce_significance(value), value)
        for value in (False, "false", "F", "No", "n", "0", " not significant ", "NS", 0):
            self.assertFalse(g.coerce_significance(value), value)
        for value in ("maybe", "", None, 2, 0.5, [1]):
            with self.assertRaises(g.SpecError):
                g.coerce_significance(value)

    def test_group_order_from_first_appearance(self):
        case = {"id": "t", "call": "pairs", "options": {}, "input": {"means": None, "pairs": [
            {"group1": "b", "group2": "a", "significant": False},
            {"group1": "c", "group2": "a", "significant": True},
            {"group1": "c", "group2": "b", "significant": False}]}}
        groups, edges, _ = g.pairs_to_graph(case)
        self.assertEqual(groups, ["b", "c", "a"])
        self.assertEqual(edges, [(0, 1), (0, 2)])

    def test_every_error_case_is_rejected_with_its_prefix(self):
        for case in g.error_cases():
            with self.assertRaises(g.SpecError, msg=case["id"]) as ctx:
                g.solve_case(case)
            self.assertEqual(ctx.exception.kind, case["expected"]["kind"], case["id"])
            self.assertTrue(ctx.exception.message.startswith(
                case["expected"]["message_prefix"]), case["id"])


class CheckerAndSetupTest(unittest.TestCase):
    def test_bad_results_differ_from_the_wheat_result(self):
        fixtures = HERE / "fixtures"
        checker = json.loads((fixtures / "checker.json").read_text(encoding="utf-8"))
        reduce = json.loads((fixtures / "reduce.json").read_text(encoding="utf-8"))
        wheat = next(c for c in reduce["cases"] if c["id"] == "hand/wheat")["expected"]
        names = {b["name"] for b in checker["bad"]}
        self.assertEqual(names, {"loses_relationship", "not_minimal"})
        for bad in checker["bad"]:
            self.assertNotEqual(bad["result"]["assignments"], wheat["assignments"])
        minimal = next(b for b in checker["bad"] if b["name"] == "not_minimal")["result"]
        self.assertEqual(minimal["stats"]["assignments_after"], 56)

    def test_python_example_copies_are_identical(self):
        for name in g.DATA_FILES:
            self.assertEqual(g.read_text(g.DATA / name), g.read_text(g.PY_EXAMPLES / name))

    def test_only_standard_library_imports(self):
        stdlib = set(sys.stdlib_module_names)
        for fname in ("generate.py", "test_generate.py"):
            tree = ast.parse((HERE / fname).read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [(node.module or "").split(".")[0]]
                for name in names:
                    self.assertTrue(name in stdlib or name == "generate",
                                    "%s imports %s" % (fname, name))

    def test_random_inputs_are_at_least_200_graphs(self):
        files, _ = g.random_inputs()
        total = sum(len(records) for _, records in files.values())
        self.assertGreaterEqual(total, 200)
        self.assertTrue(all(6 <= rec["n"] <= 12 for _, records in files.values()
                            for rec in records))
        self.assertTrue(math.isfinite(total))


if __name__ == "__main__":
    unittest.main(verbosity=1)
