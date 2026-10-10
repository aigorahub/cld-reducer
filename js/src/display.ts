import { makeLetterLabels } from "./labels.js";
/** Section 7: sort the columns, label them, and collect each group's tokens. */
export function assignLetters(columns: number[][], numGroups: number, means: number[] | null): string[][] {
  const key = (members: number[]): [number, number] => {
    const lowest = Math.min(...members);
    return means ? [-Math.max(...members.map((g) => means[g])), lowest] : [lowest, lowest];
  };
  // Array.prototype.sort is stable, so equal keys keep the canonical clique order.
  const order = columns.map((_, c) => c).sort((a, b) => {
    const [a1, a2] = key(columns[a]);
    const [b1, b2] = key(columns[b]);
    return a1 !== b1 ? (a1 < b1 ? -1 : 1) : a2 - b2;
  });
  const labels = makeLetterLabels(order.length);
  const tokens: string[][] = Array.from({ length: numGroups }, () => []);
  order.forEach((column, k) => { for (const g of columns[column]) tokens[g].push(labels[k]); });
  return tokens;
}

export function formatTokens(tokens: string[]): string {
  return tokens.every((t) => t.length === 1) ? tokens.join("") : tokens.join(" ");
}
