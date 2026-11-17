// Offsets. The server counts Unicode code points (as Python strings do); the browser's
// strings and selections count UTF-16 units. Everything sent to the server is converted.

/** The number of code points in a string. */
export function codePointLength(text: string): number {
  return [...text].length;
}

/** Convert an index in UTF-16 units into an offset in code points. */
export function utf16ToCodePoints(text: string, utf16Index: number): number {
  let index = Math.max(0, Math.min(utf16Index, text.length));
  // An index that falls between the two halves of a surrogate pair belongs before it.
  if (index > 0 && index < text.length && isLowSurrogate(text.charCodeAt(index))) {
    if (isHighSurrogate(text.charCodeAt(index - 1))) index -= 1;
  }
  return codePointLength(text.slice(0, index));
}

/** Convert an offset in code points into an index in UTF-16 units. */
export function codePointsToUtf16(text: string, codePoints: number): number {
  let index = 0;
  let remaining = Math.max(0, codePoints);
  for (const character of text) {
    if (remaining === 0) break;
    index += character.length;
    remaining -= 1;
  }
  return index;
}

/** Slice a string by code-point offsets. */
export function sliceCodePoints(text: string, start: number, end: number): string {
  return text.slice(codePointsToUtf16(text, start), codePointsToUtf16(text, end));
}

function isHighSurrogate(unit: number): boolean {
  return unit >= 0xd800 && unit <= 0xdbff;
}

function isLowSurrogate(unit: number): boolean {
  return unit >= 0xdc00 && unit <= 0xdfff;
}
