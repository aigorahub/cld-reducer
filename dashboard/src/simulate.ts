// Simulated multiple comparisons with the model of Gramm, Guo, Hüffner,
// Niedermeier, Piepho, and Schmid (2007), Section 3.2. Ennis, Fayle, and Ennis
// (2012), Section 8, generate their test graphs with this method.

/** Parameters of Section 3.2, fitted there to oilseed rape trials. */
export const MODEL = {
  meanOfMeans: 42.6,
  varianceOfMeans: 12.7,
  gammaShape: 4.12,
  gammaScale: 0.429,
  correlationMean: 0.00625,
  correlationVariance: 0.00182,
  /** A difference is significant at the 5% level when |t| exceeds this value. */
  critical: 1.96,
} as const;

/** Uniform numbers in [0, 1) from a 32-bit seed (mulberry32). */
export function uniform(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Standard normal numbers (Box-Muller). */
export function normal(rand: () => number): () => number {
  let spare: number | null = null;
  return () => {
    if (spare !== null) { const s = spare; spare = null; return s; }
    let u = 0;
    while (u === 0) u = rand();
    const r = Math.sqrt(-2 * Math.log(u));
    const angle = 2 * Math.PI * rand();
    spare = r * Math.sin(angle);
    return r * Math.cos(angle);
  };
}

/** Gamma numbers for shape >= 1 (Marsaglia and Tsang, 2000). */
export function gamma(rand: () => number, z: () => number, shape: number, scale: number): number {
  const d = shape - 1 / 3;
  const c = 1 / Math.sqrt(9 * d);
  for (;;) {
    let x: number;
    let v: number;
    do { x = z(); v = 1 + c * x; } while (v <= 0);
    v = v * v * v;
    const u = rand();
    if (u < 1 - 0.0331 * x ** 4 || Math.log(u) < 0.5 * x * x + d * (1 - v + Math.log(v))) return d * v * scale;
  }
}

/** Eigenvalues and eigenvectors (columns) of a symmetric matrix, by cyclic Jacobi rotations. */
export function symmetricEigen(matrix: readonly (readonly number[])[]): { values: number[]; vectors: number[][] } {
  const n = matrix.length;
  const a = matrix.map((row) => [...row]);
  const v = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j): number => (i === j ? 1 : 0)));
  for (let sweep = 0; sweep < 100; sweep++) {
    let off = 0;
    for (let p = 0; p < n; p++) for (let q = p + 1; q < n; q++) off += a[p][q] * a[p][q];
    if (off < 1e-22) break;
    for (let p = 0; p < n; p++) {
      for (let q = p + 1; q < n; q++) {
        if (Math.abs(a[p][q]) < 1e-300) continue;
        const theta = (a[q][q] - a[p][p]) / (2 * a[p][q]);
        const t = Math.sign(theta || 1) / (Math.abs(theta) + Math.sqrt(theta * theta + 1));
        const c = 1 / Math.sqrt(t * t + 1);
        const s = t * c;
        for (let k = 0; k < n; k++) {
          const akp = a[k][p], akq = a[k][q];
          a[k][p] = c * akp - s * akq;
          a[k][q] = s * akp + c * akq;
        }
        for (let k = 0; k < n; k++) {
          const apk = a[p][k], aqk = a[q][k];
          a[p][k] = c * apk - s * aqk;
          a[q][k] = s * apk + c * aqk;
        }
        for (let k = 0; k < n; k++) {
          const vkp = v[k][p], vkq = v[k][q];
          v[k][p] = c * vkp - s * vkq;
          v[k][q] = s * vkp + c * vkq;
        }
      }
    }
  }
  return { values: a.map((row, i) => row[i]), vectors: v };
}

export interface Experiment {
  n: number;
  seed: number;
  /** T1 to Tn, from the highest mean to the lowest. */
  groups: string[];
  means: number[];
  /** significant[i][j] is true when groups i and j differ significantly. */
  significant: boolean[][];
}

/** One simulated experiment with n treatments. The same n and seed give the same experiment. */
export function simulate(n: number, seed: number, model: { readonly [K in keyof typeof MODEL]: number } = MODEL): Experiment {
  if (!Number.isInteger(n) || n < 2) throw new RangeError("n must be a whole number of at least 2");
  const rand = uniform(Math.imul(seed >>> 0, 0x9e3779b1) ^ Math.imul(n, 0x85ebca6b));
  const z = normal(rand);
  const m = model;
  const means = Array.from({ length: n }, () => m.meanOfMeans + Math.sqrt(m.varianceOfMeans) * z());
  const variances = Array.from({ length: n }, () => gamma(rand, z, m.gammaShape, m.gammaScale));

  // Correlations tanh(z), then a repair of the eigenvalues that keeps the matrix positive definite.
  const r = Array.from({ length: n }, () => new Array<number>(n).fill(0));
  for (let i = 0; i < n; i++) {
    r[i][i] = 1;
    for (let j = i + 1; j < n; j++) {
      r[i][j] = r[j][i] = Math.tanh(m.correlationMean + Math.sqrt(m.correlationVariance) * z());
    }
  }
  const { values, vectors } = symmetricEigen(r);
  const smallest = Math.min(...values.filter((d) => d > 0));
  const repaired = values.map((d) => (d > 0 ? d : smallest));
  // R = Q diag(d) Q'. Section 3.2 keeps the diagonal as it is. The paper says that it can fall
  // below 1, but a larger eigenvalue adds a positive semidefinite term, so it can only rise above 1.
  const corr = Array.from({ length: n }, (_, i) => Array.from({ length: n }, (_, j) => {
    let sum = 0;
    for (let k = 0; k < n; k++) sum += vectors[i][k] * repaired[k] * vectors[j][k];
    return sum;
  }));
  const cov = (i: number, j: number): number => Math.sqrt(variances[i] * variances[j]) * corr[i][j];

  const order = means.map((_, i) => i).sort((a, b) => means[b] - means[a]);
  const significant = order.map((i) => order.map((j) => {
    if (i === j) return false;
    const variance = cov(i, i) + cov(j, j) - 2 * cov(i, j);
    const difference = means[i] - means[j];
    if (variance <= 0) return difference !== 0;
    return Math.abs(difference / Math.sqrt(variance)) > m.critical;
  }));
  return { n, seed, groups: order.map((_, k) => `T${k + 1}`), means: order.map((i) => means[i]), significant };
}

/** The experiment as the two input files of the page. Means have three decimals. */
export function experimentCsv(e: Experiment): { pairs: string; means: string } {
  const pairs = ["group1,group2,significant"];
  for (let i = 0; i < e.n; i++) {
    for (let j = i + 1; j < e.n; j++) pairs.push(`${e.groups[i]},${e.groups[j]},${e.significant[i][j]}`);
  }
  const means = ["group,mean", ...e.groups.map((g, i) => `${g},${e.means[i].toFixed(3)}`)];
  return { pairs: pairs.join("\n") + "\n", means: means.join("\n") + "\n" };
}

/** The adjacency of the clique membership matrix of Table II of the 2012 paper. */
export const TABLE_II = (() => {
  const members = [
    [1, 1, 1, 0, 0, 0, 0], [1, 1, 0, 1, 0, 1, 0], [1, 1, 0, 1, 0, 1, 0], [0, 0, 1, 0, 1, 0, 1],
    [1, 0, 0, 1, 0, 0, 0], [0, 0, 0, 1, 1, 0, 0], [0, 1, 1, 0, 0, 1, 1], [0, 0, 0, 1, 1, 1, 1],
  ];
  const n = members.length;
  const rows = ["group1,group2,significant"];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      const share = members[i].some((on, c) => on === 1 && members[j][c] === 1);
      rows.push(`${i + 1},${j + 1},${!share}`);
    }
  }
  return rows.join("\n") + "\n";
})();
