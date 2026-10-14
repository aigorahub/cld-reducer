"""Independent essential decision oracle, using full Boolean reconstruction."""

from itertools import combinations


def maximal_cliques(adjacency):
    n = len(adjacency)
    candidates = [
        s for k in range(1, n + 1) for s in combinations(range(n), k)
        if all(adjacency[u][v] for u, v in combinations(s, 2))
    ]
    return sorted(c for c in candidates if not any(set(c) < set(d) for d in candidates))


def covered(adjacency, columns):
    return all(
        bool(adjacency[u][v]) == any(u in c and v in c for c in columns)
        for u in range(len(adjacency)) for v in range(len(adjacency))
    )


def scan_case(case_id, adjacency, weights):
    cliques = maximal_cliques(adjacency)
    assert covered(adjacency, cliques)
    essential_sigma = []
    column = 0
    for c, clique in enumerate(cliques):
        for v in clique:
            trial = list(cliques)
            trial[c] = tuple(u for u in clique if u != v)
            if not covered(adjacency, trial):
                essential_sigma.append(column)
            column += 1
    essential_c = [
        c for c in range(len(cliques))
        if not covered(adjacency, cliques[:c] + cliques[c + 1:])
    ]
    return {
        "id": case_id, "adjacency": adjacency, "weights": weights,
        "cliques": cliques, "essential_sigma": essential_sigma, "essential_c": essential_c,
    }


def graph(n, edges):
    adjacency = [[int(u == v) for v in range(n)] for u in range(n)]
    for u, v in edges:
        adjacency[u][v] = adjacency[v][u] = 1
    return adjacency


def reduced(adjacency):
    classes = {}
    for v, row in enumerate(adjacency):
        classes.setdefault(tuple(row), []).append(v)
    representatives = [vertices[0] for vertices in classes.values()]
    return (
        [[adjacency[u][v] for v in representatives] for u in representatives],
        [len(vertices) for vertices in classes.values()],
    )


def cases():
    result = []

    def add(case_id, adjacency):
        result.append(scan_case(case_id + "/original", adjacency, [1] * len(adjacency)))
        quotient, weights = reduced(adjacency)
        result.append(scan_case(case_id + "/reduced", quotient, weights))

    for n in range(1, 6):
        pairs = list(combinations(range(n), 2))
        for mask in range(1 << len(pairs)):
            add(f"n{n}/{mask}", graph(n, [p for k, p in enumerate(pairs) if mask >> k & 1]))
    add("sigma-conflict", graph(5, [(0,1),(0,2),(0,3),(0,4),(1,3),(1,4),(2,3),(2,4)]))
    add("c-conflict", graph(6, [(0,2),(0,3),(0,4),(0,5),(1,2),(1,3),(1,4),(1,5),(2,3),(2,5),(3,4)]))
    add("no-essential", graph(6, [(u,v) for u,v in combinations(range(6), 2) if u // 2 != v // 2]))
    classes = [0, 1, 0, 2, 1, 0, 2]
    add("interleaved-weighted", [
        [int(abs(u - v) <= 1) for v in classes] for u in classes
    ])
    return result
