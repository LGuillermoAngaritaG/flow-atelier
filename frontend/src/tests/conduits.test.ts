import { describe, it, expect, afterEach } from "vitest";
import {
  conduits,
  getConduit,
  mockGetConduits,
  mockGetConduit,
  mockOpenPath,
  mockCreateConduit,
} from "@/services/mock/conduits";

const ORIGINAL_LENGTH = conduits.length;

afterEach(() => {
  while (conduits.length > ORIGINAL_LENGTH) conduits.pop();
});

describe("getConduit", () => {
  it("returns conduit for known name", () => {
    const c = getConduit("release_notes");
    expect(c).toBeDefined();
    expect(c!.name).toBe("release_notes");
  });

  it("returns undefined for unknown name", () => {
    expect(getConduit("nonexistent")).toBeUndefined();
  });

  it("matches names case-sensitively", () => {
    expect(getConduit("Release_Notes")).toBeUndefined();
  });
});

describe("mockGetConduits", () => {
  it("returns the full conduits array", () => {
    const result = mockGetConduits();
    expect(result.length).toBeGreaterThanOrEqual(6);
    expect(result[0].name).toBe("release_notes");
  });
});

describe("mockGetConduit", () => {
  it("returns conduit for known name", () => {
    const c = mockGetConduit("deploy_pipeline");
    expect(c).toBeDefined();
    expect(c!.name).toBe("deploy_pipeline");
  });

  it("returns undefined for unknown name", () => {
    expect(mockGetConduit("nope")).toBeUndefined();
  });
});

describe("mockOpenPath", () => {
  it("returns { opened: true } for existing conduit", () => {
    expect(mockOpenPath("release_notes")).toEqual({ opened: true });
  });

  it("returns { opened: false } for unknown conduit", () => {
    expect(mockOpenPath("nonexistent")).toEqual({ opened: false });
  });
});

describe("mockCreateConduit", () => {
  it("creates and returns a new conduit", () => {
    const created = mockCreateConduit({
      name: "new_conduit",
      description: "A new one",
      tasks: [],
    });
    expect(created.name).toBe("new_conduit");
    expect(created.description).toBe("A new one");
    expect(created.inputs).toEqual({});
    expect(created.runPath).toBe("");
  });

  it("throws on duplicate conduit name", () => {
    expect(() =>
      mockCreateConduit({
        name: "release_notes",
        description: "Duplicate",
        tasks: [],
      }),
    ).toThrow('Conduit "release_notes" already exists');
  });
});
