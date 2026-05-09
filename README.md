# cld-reducer

`cld-reducer` is a Python package for reducing Compact Letter Displays (CLDs)
while preserving the pairwise statistical relationships encoded by the display.

The first implementation is an assignment-minimum reducer for post-hoc
comparison tables. The package is intentionally structured so additional CLD
reduction algorithms can be added later.

## Planned Interface

```python
from cld_reducer import reduce_letters

result = reduce_letters(post_hoc_results, means, method="assignment_minimum")
print(result.letters)
print(result.stats)
```

Command-line usage will be available as:

```bash
cld-reduce pairs.csv --means means.csv --out reduced.csv
```

This repository is being prepared as a reference implementation for CLD
letter-reduction work presented at Sensometrics 2026.
