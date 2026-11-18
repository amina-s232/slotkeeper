import { describe, expect, it } from "vitest";
import { hueFor, initials } from "./initials";

describe("initials", () => {
  it("uses the first letters of the first two words", () => {
    expect(initials("Dr Rao")).toBe("DR");
    expect(initials("Asha Nair Menon")).toBe("AN");
  });
  it("handles one word, extra spaces and lower case", () => {
    expect(initials("sam")).toBe("S");
    expect(initials("  asha   nair ")).toBe("AN");
  });
  it("never returns an empty string", () => {
    expect(initials("   ")).toBe("?");
    expect(initials("")).toBe("?");
  });
});

describe("hueFor", () => {
  it("is stable and within the colour wheel", () => {
    expect(hueFor("Dr Rao")).toBe(hueFor("Dr Rao"));
    for (const name of ["Dr Rao", "Dr Hughes", "Sam", "", "日本語"]) {
      const hue = hueFor(name);
      expect(hue).toBeGreaterThanOrEqual(0);
      expect(hue).toBeLessThan(360);
    }
  });
  it("gives different people different colours", () => {
    expect(hueFor("Dr Rao")).not.toBe(hueFor("Dr Hughes"));
  });
});
