import { describe, it, expect } from "vitest";
import { toCamelCase, toSnakeCase } from "@/services/transforms";

describe("toCamelCase", () => {
  it("returns primitives unchanged", () => {
    expect(toCamelCase("hello")).toBe("hello");
    expect(toCamelCase(42)).toBe(42);
    expect(toCamelCase(true)).toBe(true);
    expect(toCamelCase(null)).toBe(null);
    expect(toCamelCase(undefined)).toBe(undefined);
  });

  it("converts flat snake_case object to camelCase", () => {
    expect(toCamelCase({ first_name: "Ada", last_name: "Lovelace" })).toEqual({
      firstName: "Ada",
      lastName: "Lovelace",
    });
  });

  it("converts nested objects recursively", () => {
    expect(
      toCamelCase({ user_info: { first_name: "Ada", home_address: { zip_code: "12345" } } }),
    ).toEqual({
      userInfo: { firstName: "Ada", homeAddress: { zipCode: "12345" } } ,
    });
  });

  it("converts objects inside arrays recursively", () => {
    expect(
      toCamelCase([{ item_name: "A" }, { item_name: "B" }]),
    ).toEqual([{ itemName: "A" }, { itemName: "B" }]);
  });

  it("returns empty object as-is", () => {
    expect(toCamelCase({})).toEqual({});
  });

  it("returns empty array as-is", () => {
    expect(toCamelCase([])).toEqual([]);
  });

  it("leaves already-camelCase keys unchanged", () => {
    expect(toCamelCase({ firstName: "Ada" })).toEqual({ firstName: "Ada" });
  });

  it("handles keys with multiple consecutive underscores", () => {
    expect(toCamelCase({ a__b: 1 })).toEqual({ a_B: 1 });
  });

  it("handles numeric values in objects", () => {
    expect(toCamelCase({ max_count: 10, is_active: 1 })).toEqual({ maxCount: 10, isActive: 1 });
  });
});

describe("toSnakeCase", () => {
  it("returns primitives unchanged", () => {
    expect(toSnakeCase("hello")).toBe("hello");
    expect(toSnakeCase(42)).toBe(42);
    expect(toSnakeCase(true)).toBe(true);
    expect(toSnakeCase(null)).toBe(null);
    expect(toSnakeCase(undefined)).toBe(undefined);
  });

  it("converts flat camelCase object to snake_case", () => {
    expect(toSnakeCase({ firstName: "Ada", lastName: "Lovelace" })).toEqual({
      first_name: "Ada",
      last_name: "Lovelace",
    });
  });

  it("converts nested objects recursively", () => {
    expect(
      toSnakeCase({ userInfo: { firstName: "Ada", homeAddress: { zipCode: "12345" } } }),
    ).toEqual({
      user_info: { first_name: "Ada", home_address: { zip_code: "12345" } },
    });
  });

  it("converts objects inside arrays recursively", () => {
    expect(toSnakeCase([{ itemName: "A" }, { itemName: "B" }])).toEqual([
      { item_name: "A" },
      { item_name: "B" },
    ]);
  });

  it("returns empty object as-is", () => {
    expect(toSnakeCase({})).toEqual({});
  });

  it("returns empty array as-is", () => {
    expect(toSnakeCase([])).toEqual([]);
  });

  it("leaves already-snake_case keys unchanged", () => {
    expect(toSnakeCase({ first_name: "Ada" })).toEqual({ first_name: "Ada" });
  });
});
