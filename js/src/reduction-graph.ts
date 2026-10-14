// Lemma 2.5: identical closed neighborhoods share one weighted vertex.
export function reduceGraphVertices(adjacency: boolean[][]): {
  adjacency: boolean[][]; classes: number[][]; weights: number[];
} {
  const byRow = new Map<string, number[]>();
  adjacency.forEach((row, vertex) => {
    const key = row.map(value => value ? "1" : "0").join("");
    const group = byRow.get(key);
    if (group) group.push(vertex);
    else byRow.set(key, [vertex]);
  });
  const classes = [...byRow.values()];
  return {
    adjacency: classes.map(a => classes.map(b => adjacency[a[0]][b[0]])),
    classes, weights: classes.map(group => group.length),
  };
}

export function expandGraphColumns(columns: number[][], classes: number[][]): number[][] {
  return columns.map(column => column.flatMap(c => classes[c]).sort((a, b) => a - b));
}
