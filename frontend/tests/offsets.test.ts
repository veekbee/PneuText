import { describe, expect, it } from "vitest";

import {
  codePointLength,
  codePointsToUtf16,
  sliceCodePoints,
  utf16ToCodePoints,
} from "../src/lib/offsets";

// U+1D11E (a musical clef) is one code point but two UTF-16 units.
const CLEF = "\u{1D11E}";
const TEXT = `red ${CLEF} beside ${CLEF}${CLEF} it`;

describe("offsets", () => {
  it("counts code points, not UTF-16 units", () => {
    expect(TEXT.length).toBe(21);
    expect(codePointLength(TEXT)).toBe(18);
    expect(codePointLength("")).toBe(0);
    expect(codePointLength("café")).toBe(4);
  });

  it("converts a UTF-16 index to a code-point offset", () => {
    expect(utf16ToCodePoints(TEXT, 0)).toBe(0);
    expect(utf16ToCodePoints(TEXT, 4)).toBe(4); // just before the first clef
    expect(utf16ToCodePoints(TEXT, 6)).toBe(5); // just after it
    expect(utf16ToCodePoints(TEXT, TEXT.indexOf("beside"))).toBe(6);
    expect(utf16ToCodePoints(TEXT, TEXT.length)).toBe(18);
  });

  it("treats an index inside a surrogate pair as the position before it", () => {
    expect(utf16ToCodePoints(TEXT, 5)).toBe(4);
  });

  it("clamps indexes outside the string", () => {
    expect(utf16ToCodePoints(TEXT, -3)).toBe(0);
    expect(utf16ToCodePoints(TEXT, 999)).toBe(18);
  });

  it("converts a code-point offset back to a UTF-16 index", () => {
    expect(codePointsToUtf16(TEXT, 0)).toBe(0);
    expect(codePointsToUtf16(TEXT, 5)).toBe(6);
    expect(codePointsToUtf16(TEXT, 6)).toBe(TEXT.indexOf("beside"));
    expect(codePointsToUtf16(TEXT, 999)).toBe(TEXT.length);
  });

  it("round-trips every position", () => {
    for (let offset = 0; offset <= codePointLength(TEXT); offset += 1) {
      expect(utf16ToCodePoints(TEXT, codePointsToUtf16(TEXT, offset))).toBe(offset);
    }
  });

  it("slices by code points without splitting a character", () => {
    expect(sliceCodePoints(TEXT, 6, 12)).toBe("beside");
    expect(sliceCodePoints(TEXT, 4, 5)).toBe(CLEF);
    expect(sliceCodePoints(TEXT, 13, 15)).toBe(CLEF + CLEF);
  });
});
