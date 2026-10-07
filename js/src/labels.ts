// Spreadsheet style letter labels: A to Z, then AA to AZ, BA, and so on.

export function makeLetterLabels(count: number): string[] {
  if (!Number.isInteger(count) || count < 0) {
    throw new RangeError("count must be a non-negative whole number");
  }
  const labels: string[] = [];
  for (let index = 0; index < count; index++) {
    let value = index;
    let label = "";
    for (;;) {
      label = String.fromCharCode(65 + (value % 26)) + label;
      value = Math.floor(value / 26);
      if (value === 0) break;
      value -= 1;
    }
    labels.push(label);
  }
  return labels;
}
