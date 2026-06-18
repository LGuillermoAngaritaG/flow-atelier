import { describe, it, expect } from "vitest";
import { escapeRegExp } from "@/utils/regex";

describe("escapeRegExp", () => {
  it("escapes regex metacharacters so a name matches only itself", () => {
    const name = "a.b(c)*";
    const re = new RegExp(`\\{\\{inputs\\.${escapeRegExp(name)}\\}\\}`, "g");
    // exact ref is removed
    expect("x {{inputs.a.b(c)*}} y".replace(re, "")).toBe("x  y");
    // a non-matching-but-regex-similar string is left intact
    expect("{{inputs.aXbZcW}}".replace(re, "")).toBe("{{inputs.aXbZcW}}");
  });

  it("is a no-op for plain alphanumeric names", () => {
    expect(escapeRegExp("my_input1")).toBe("my_input1");
  });
});
