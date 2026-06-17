// @vitest-environment jsdom
import { describe, it, expect, beforeEach } from "vitest";
import { loadProjects } from "@/services/storage/projects";
import { PROJECTS_KEY } from "@/constants/kanban";

beforeEach(() => localStorage.clear());

describe("loadProjects shape validation", () => {
  it("returns the default project when nothing is stored", () => {
    expect(loadProjects()).toEqual([{ id: "default", name: "my project" }]);
  });

  it("returns stored array as-is", () => {
    const projects = [{ id: "a", name: "A" }];
    localStorage.setItem(PROJECTS_KEY, JSON.stringify(projects));
    expect(loadProjects()).toEqual(projects);
  });

  it("falls back to default when stored value is not an array", () => {
    localStorage.setItem(PROJECTS_KEY, JSON.stringify({ not: "an array" }));
    expect(loadProjects()).toEqual([{ id: "default", name: "my project" }]);
  });

  it("falls back to default on corrupted JSON", () => {
    localStorage.setItem(PROJECTS_KEY, "{not json");
    expect(loadProjects()).toEqual([{ id: "default", name: "my project" }]);
  });
});
