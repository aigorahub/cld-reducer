# Paper context for the essential scan

Source: Ennis, Fayle, and Ennis (2012), Assignment-Minimum Clique Coverings,
ACM Journal of Experimental Algorithmics 17, Article 1.5.
DOI: https://doi.org/10.1145/2133803.2275596.

The user supplied a PDF and a checked Markdown conversion. Local sources:

- `/Users/john/aigora/dev/cld-reducer-submission-artifacts/papers/assignment-minimum-clique-coverings-2012.pdf`
- `/Users/john/aigora/dev/cld-reducer-submission-artifacts/papers/assignment-minimum-clique-coverings-2012.md`
- `/Users/john/aigora/dev/cld-reducer-submission-artifacts/papers/assignment-minimum-clique-coverings-2012-conversion-notes.md`

PDF SHA-256: `4f0f8fd7a2b8bb37122f78ac3159ecf0cb5cb4af1a3c4c6e3a9c721bc9bf57b7`.
Markdown SHA-256: `b4a226981ecc3db44f31256546f1b5c3f491e2bfaaef23d00e162aa9b704f613`.

This note states the relevant mathematics in plain notation. It is not a new
conversion or a replacement for the source paper.

Definition 1.1 requires a clique covering to cover every vertex and every edge.
Definition 2.1 defines a binary membership matrix M with vertices as rows and
cliques as columns. The adjacency matrix has a unit diagonal.
Lemma 2.2 states that coverage is equivalent to M *B transpose(M) = adjacency,
where *B is Boolean matrix multiplication.

Definition 2.3 calls the set of all maximal cliques the maximal covering.
Lemma 2.4 proves that at least one assignment minimum is a subcovering of it.
Lemma 2.5 establishes an optimum in which vertices with identical closed
neighborhoods use the same membership pattern. Combine them and count each
membership by the size of its class. It does not state that every optimum
already has uniform patterns. PR 7's separate canonical proof explains why
the canonical optimum has uniform patterns.

Definition 3.1 calls an assignment removable if deleting it gives another valid
covering. Algorithm 3.1, FIND-AM, uses backtracking with removable and previously
visited assignment sets to enumerate assignment-minimal subcoverings. Theorem
3.3 establishes that enumeration. An assignment-minimal cover can have a higher
cost than an assignment-minimum cover. FIND-AM is outside the proposed update.

Section 4 tests deletion by setting one entry of M to zero and checking that
the Boolean product still equals the original adjacency matrix. Only required
relationships incident to that vertex can be lost. Check its row against each
adjacent vertex, including its own diagonal entry. Bit operations can implement
these Boolean inner products.

One source sentence says that only the corresponding row of the product can
change. The corresponding column can also change. The product is symmetric,
so checking the row remains sufficient. The proposed plan uses that valid test.

For a full cover, deletion of membership (c, v) loses edge {v, u} exactly when
c is the only clique containing both endpoints. It loses diagonal coverage
exactly when c is v's only clique. For deletion of a whole clique, a vertex or
edge becomes uncovered exactly when that clique is its sole covering column.
These equivalences follow directly from the Boolean coverage condition.

Section 7 maps letter display rows to treatments and letter columns to cliques.
The five treatment example uses maximal cliques {1,2,3}, {2,3,4}, {3,4,5}.
It has nine memberships initially. The center vertex's membership in the middle
clique is removable. The other eight memberships are required in this full cover.
