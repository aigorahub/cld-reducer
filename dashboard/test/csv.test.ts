import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DataError, MAX_CHARS, TEMPLATE_MEANS, TEMPLATE_PAIRS, detectDelimiter, parseDelimited, parseMeans,
         parsePairs } from "../src/csv.js";

const data = (name: string): string =>
  readFileSync(new URL(`../../conformance/data/${name}`, import.meta.url), "utf8");

describe("parseDelimited", () => {
  it("splits rows and keeps the first line of each row", () => {
    expect(parseDelimited("a,b\n1,2\r\n\r\n3,4", ",")).toEqual([
      { fields: ["a", "b"], line: 1 }, { fields: ["1", "2"], line: 2 }, { fields: ["3", "4"], line: 4 },
    ]);
  });

  it("removes spaces around a value without quotes and keeps a value in quotes", () => {
    expect(parseDelimited(' a , "  b " ,c ', ",")[0].fields).toEqual(["a", "  b ", "c"]);
  });

  it("reads quotes, doubled quotes, and delimiters and line ends inside quotes", () => {
    const rows = parseDelimited('"x, ""y""","line 1\nline 2"\nnext,row', ",");
    expect(rows).toEqual([
      { fields: ['x, "y"', "line 1\nline 2"], line: 1 }, { fields: ["next", "row"], line: 3 },
    ]);
  });

  it("keeps a row of empty values and leaves out a blank line", () => {
    expect(parseDelimited("a,b\n,\n   \n", ",").map((r) => r.fields)).toEqual([["a", "b"], ["", ""]]);
    expect(parseDelimited('""', ",")).toEqual([{ fields: [""], line: 1 }]);
  });

  it("reports a quote that does not close and text after a closing quote", () => {
    expect(() => parseDelimited('a,b\n"open,1', ",")).toThrow(new DataError("Line 2: a quoted value has no closing quote."));
    expect(() => parseDelimited('"a"x,b', ",")).toThrow("Line 1: text follows a closing quote.");
  });
});

describe("detectDelimiter", () => {
  it("takes the most frequent of tab, semicolon, and comma in the first line", () => {
    expect(detectDelimiter("group1,group2,significant\n1;2;3")).toBe(",");
    expect(detectDelimiter("group1;group2;significant")).toBe(";");
    expect(detectDelimiter("group1\tgroup2\tsignificant")).toBe("\t");
    expect(detectDelimiter('"a,b,c";d;e')).toBe(";");
    expect(detectDelimiter("one")).toBe(",");
  });
});

describe("parsePairs", () => {
  it("reads the three columns as text, in any order and letter case, and ignores other columns", () => {
    const rows = parsePairs("﻿Significant;note;Group2;GROUP1\nns;x;b;a\n 1 ;y;\" c\";a\n");
    expect(rows).toEqual([
      { group1: "a", group2: "b", significant: "ns" },
      { group1: "a", group2: " c", significant: "1" },
    ]);
  });

  it("reads the example files of the repository", () => {
    const simple = parsePairs(data("simple_abc_to_ac_pairs.csv"));
    expect(simple).toHaveLength(10);
    expect(simple[2]).toEqual({ group1: "1", group2: "4", significant: "true" });
    // The wheat file has CRLF line ends.
    const wheat = parsePairs(data("piepho2004_wheat_pairs.csv"));
    expect(wheat).toHaveLength(190);
    expect(new Set(wheat.map((r) => r.significant))).toEqual(new Set(["true", "false"]));
  });

  it("accepts a header row without decisions, which the package then checks", () => {
    expect(parsePairs("group1,group2,significant\n")).toEqual([]);
  });

  it("reports text that is not a decisions table", () => {
    expect(() => parsePairs("  \n")).toThrow("Give the pairwise decisions.");
    expect(() => parsePairs("1,2,false\n1,3,true")).toThrow(
      "The first row of the decisions must name the columns group1, group2, and significant. " +
      "It does not have group1, group2, and significant.");
    expect(() => parsePairs("group1,group2\na,b")).toThrow("It does not have significant.");
    expect(() => parsePairs("group1,group2,significant,GROUP1\na,b,no,c")).toThrow(
      "The first row of the decisions names the column group1 more than once.");
    expect(() => parsePairs("group1,group2,significant\na,b,no\na,c")).toThrow(
      "Line 3 has 2 values, but the first row has 3 columns.");
    expect(() => parsePairs("x".repeat(MAX_CHARS + 1))).toThrow(/The page reads up to 5,000,000\.$/);
  });

  it("throws DataError", () => {
    expect(() => parsePairs("")).toThrow(DataError);
  });
});

describe("parseMeans", () => {
  it("reads no means from blank text", () => {
    expect(parseMeans(" \n")).toBeNull();
  });

  it("reads groups as text and means as numbers", () => {
    expect(parseMeans(data("simple_abc_to_ac_means.csv"))).toEqual([
      { group: "1", mean: 3.73 }, { group: "2", mean: 3.57 }, { group: "3", mean: 3.46 },
      { group: "4", mean: 3.33 }, { group: "5", mean: 3.3 },
    ]);
    expect(parseMeans("mean,group\n-1e2,a\n.5,b")).toEqual([{ group: "a", mean: -100 }, { group: "b", mean: 0.5 }]);
  });

  it("reads a decimal comma with semicolons or tabs only", () => {
    expect(parseMeans("group;mean\na;3,5")).toEqual([{ group: "a", mean: 3.5 }]);
    expect(() => parseMeans('group,mean\na,"3,5"')).toThrow('Line 2: the mean "3,5" of group "a" is not a number.');
  });

  it("reports a mean that is missing or not a finite number", () => {
    expect(() => parseMeans("group,mean\na,")).toThrow('Line 2: group "a" has no mean.');
    expect(() => parseMeans("group,mean\na,1\nb,high")).toThrow('Line 3: the mean "high" of group "b" is not a number.');
    expect(() => parseMeans("group,mean\na,1e999")).toThrow("is not a number");
    expect(() => parseMeans("group,mean\na,0x10")).toThrow("is not a number");
    expect(() => parseMeans("group,value\na,1")).toThrow(
      "The first row of the means must name the columns group and mean. It does not have mean.");
  });
});

describe("templates", () => {
  it("hold every pair of four groups and one mean for each group", () => {
    const pairs = parsePairs(TEMPLATE_PAIRS);
    const means = parseMeans(TEMPLATE_MEANS)!;
    expect(pairs).toHaveLength(6);
    expect(means.map((m) => m.group)).toEqual(["Control", "Low dose", "Mid dose", "High dose"]);
    expect(new Set(pairs.flatMap((p) => [p.group1, p.group2]))).toEqual(new Set(means.map((m) => m.group)));
  });
});
