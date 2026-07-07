import { describe, expect, it } from "vitest";

import { sanitizeTelegramHtml } from "../lib/telegramHtml";

describe("sanitizeTelegramHtml", () => {
  it("keeps Telegram inline formatting tags", () => {
    expect(sanitizeTelegramHtml("<b>bold</b> <i>it</i> <code>x</code>")).toBe(
      "<b>bold</b> <i>it</i> <code>x</code>",
    );
  });

  it("drops an img with an onerror handler entirely", () => {
    expect(sanitizeTelegramHtml('<img src=x onerror="alert(1)">')).toBe("");
  });

  it("strips event handlers / attributes from allowed tags", () => {
    // onclick + style are not re-emitted; only the tag survives.
    expect(sanitizeTelegramHtml('<b onclick="alert(1)" style="x">hi</b>')).toBe("<b>hi</b>");
  });

  it("removes a javascript: href but keeps the link text", () => {
    expect(sanitizeTelegramHtml('<a href="javascript:alert(1)">click</a>')).toBe("click");
  });

  it("keeps a safe http(s) href on a link", () => {
    expect(sanitizeTelegramHtml('<a href="https://t.me/x">go</a>')).toBe(
      '<a href="https://t.me/x">go</a>',
    );
  });

  it("unwraps disallowed wrappers but keeps their safe inner formatting", () => {
    expect(sanitizeTelegramHtml('<div onmouseover="x()"><b>kept</b></div>')).toBe("<b>kept</b>");
  });

  it("neutralizes a script tag into inert escaped text", () => {
    const out = sanitizeTelegramHtml("<script>alert(1)</script>");
    expect(out).not.toContain("<script>");
    expect(out.toLowerCase()).not.toContain("<script");
  });

  it("escapes stray angle brackets in text", () => {
    expect(sanitizeTelegramHtml("2 < 3 & 4 > 1")).toBe("2 &lt; 3 &amp; 4 &gt; 1");
  });

  it("handles empty / falsy input", () => {
    expect(sanitizeTelegramHtml("")).toBe("");
  });

  it("strips an svg onload payload", () => {
    expect(sanitizeTelegramHtml('<svg onload="alert(1)"></svg>')).toBe("");
  });
});
