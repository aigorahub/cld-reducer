// Read the two input tables of the page (README.md, "Input format").
//
// - Commas, semicolons, or tabs between values. Quoted values. UTF-8, with or
//   without a byte order mark. LF or CRLF line ends.
// - The first row holds the column names. Their case does not matter.
// - Spaces around a value without quotes are removed. A value in quotes stays
//   as it is.
// - The decisions need the columns group1, group2, and significant. The page
//   does not read the decision words. The package does, with the rules of
//   docs/algorithm.md section 1.
// - The means need the columns group and mean. With semicolons or tabs, a
//   decimal comma is accepted.

/** One pairwise decision, as text. The keys are the default column names of the package. */
export type PairRow = { group1: string; group2: string; significant: string };
export type MeanRow = { group: string; mean: number };

export class DataError extends Error {
  override name = "DataError";
}

export const MAX_CHARS = 5_000_000;

const NUMBER = /^[+-]?(\d+(\.\d*)?|\.\d+)([eE][+-]?\d+)?$/;

interface Row {
  fields: string[];
  /** Line of the first character of the row. */
  line: number;
}

/** Split delimited text into rows. Blank lines are left out. */
export function parseDelimited(text: string, delimiter: string): Row[] {
  const rows: Row[] = [];
  let fields: string[] = [];
  let field = "";
  let inQuotes = false;
  let hadQuotes = false;
  let line = 1;
  let start = 1;
  const endField = () => {
    fields.push(hadQuotes ? field : field.trim());
    field = "";
    hadQuotes = false;
  };
  const endRow = () => {
    const blank = fields.length === 0 && !hadQuotes && field.trim() === "";
    endField();
    if (!blank) rows.push({ fields, line: start });
    fields = [];
  };
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQuotes) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; } else inQuotes = false;
      } else {
        if (c === "\n") line++;
        field += c;
      }
    } else if (c === delimiter) {
      endField();
    } else if (c === "\r" || c === "\n") {
      endRow();
      if (c === "\r" && text[i + 1] === "\n") i++;
      line++;
      start = line;
    } else if (hadQuotes) {
      if (c !== " " && c !== "\t") throw new DataError(`Line ${line}: text follows a closing quote.`);
    } else if (c === '"' && field.trim() === "") {
      inQuotes = true;
      hadQuotes = true;
      field = "";
    } else {
      field += c;
    }
  }
  if (inQuotes) throw new DataError(`Line ${start}: a quoted value has no closing quote.`);
  if (fields.length > 0 || hadQuotes || field.trim() !== "") endRow();
  return rows;
}

/** The delimiter of the first line: tab, semicolon, or comma, whichever is most frequent. */
export function detectDelimiter(text: string): string {
  let inQuotes = false;
  const counts: Record<string, number> = { "\t": 0, ";": 0, ",": 0 };
  for (const c of text) {
    if (c === '"') inQuotes = !inQuotes;
    else if (!inQuotes && (c === "\n" || c === "\r")) break;
    else if (!inQuotes && c in counts) counts[c]++;
  }
  let best = ",";
  for (const d of ["\t", ";", ","]) if (counts[d] > counts[best]) best = d;
  return best;
}

/** A value in quotes for a message, shortened when it is long. */
export function quote(value: string): string {
  return `"${value.length > 40 ? value.slice(0, 39) + "…" : value}"`;
}

function list(names: readonly string[]): string {
  if (names.length <= 2) return names.join(" and ");
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

interface Table {
  /** Position of each wanted column. */
  at: number[];
  body: Row[];
  delimiter: string;
}

function readTable(text: string, wanted: readonly string[], what: string): Table {
  if (text.length > MAX_CHARS) {
    throw new DataError(`The ${what} have ${text.length.toLocaleString("en-US")} characters. ` +
                        `The page reads up to ${MAX_CHARS.toLocaleString("en-US")}.`);
  }
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  const delimiter = detectDelimiter(text);
  const rows = parseDelimited(text, delimiter);
  if (rows.length === 0) throw new DataError(`The ${what} are empty.`);
  const header = rows[0].fields.map((name) => name.toLowerCase());
  const absent = wanted.filter((name) => !header.includes(name));
  if (absent.length > 0) {
    throw new DataError(`The first row of the ${what} must name the columns ${list(wanted)}. ` +
                        `It does not have ${list(absent)}.`);
  }
  const repeated = wanted.filter((name) => header.indexOf(name) !== header.lastIndexOf(name));
  if (repeated.length > 0) {
    throw new DataError(`The first row of the ${what} names the column ${list(repeated)} more than once.`);
  }
  const body = rows.slice(1);
  for (const row of body) {
    if (row.fields.length !== header.length) {
      throw new DataError(
        `Line ${row.line} has ${row.fields.length} ${row.fields.length === 1 ? "value" : "values"}, ` +
        `but the first row has ${header.length} ${header.length === 1 ? "column" : "columns"}.`);
    }
  }
  return { at: wanted.map((name) => header.indexOf(name)), body, delimiter };
}

/** Read the pairwise decisions. The cells stay text: the package checks them. */
export function parsePairs(text: string): PairRow[] {
  if (text.trim() === "") throw new DataError("Give the pairwise decisions.");
  const { at, body } = readTable(text, ["group1", "group2", "significant"], "decisions");
  return body.map((row) => ({
    group1: row.fields[at[0]], group2: row.fields[at[1]], significant: row.fields[at[2]],
  }));
}

/** Read the means. Blank text means that there are no means. */
export function parseMeans(text: string): MeanRow[] | null {
  if (text.trim() === "") return null;
  const { at, body, delimiter } = readTable(text, ["group", "mean"], "means");
  return body.map((row) => {
    const group = row.fields[at[0]];
    const raw = row.fields[at[1]].trim();
    const value = delimiter !== "," && /^[+-]?\d+,\d+$/.test(raw) ? raw.replace(",", ".") : raw;
    if (raw === "") throw new DataError(`Line ${row.line}: group ${quote(group)} has no mean.`);
    const mean = NUMBER.test(value) ? Number(value) : NaN;
    if (!Number.isFinite(mean)) {
      throw new DataError(`Line ${row.line}: the mean ${quote(raw)} of group ${quote(group)} is not a number.`);
    }
    return { group, mean };
  });
}

/** Small template files. The decisions form a chain: each group equals its neighbors only. */
export const TEMPLATE_PAIRS = [
  "group1,group2,significant",
  "Control,Low dose,false",
  "Control,Mid dose,true",
  "Control,High dose,true",
  "Low dose,Mid dose,false",
  "Low dose,High dose,true",
  "Mid dose,High dose,false",
].join("\n") + "\n";

export const TEMPLATE_MEANS = [
  "group,mean",
  "Control,4.1",
  "Low dose,4.6",
  "Mid dose,5.2",
  "High dose,5.9",
].join("\n") + "\n";
