import { describe, it, expect } from "vitest";
import { normalizeTemplate, sortFilesWithPrimaryFirst } from "./templateHelpers";

describe("normalizeTemplate", () => {
  it("uses createdAtInSeconds and updatedAtInSeconds from API when present", () => {
    const createdSec = Math.floor(new Date("2025-06-15T10:30:00.000Z").getTime() / 1000);
    const updatedSec = Math.floor(new Date("2025-06-16T12:00:00.000Z").getTime() / 1000);
    const raw = {
      id: 1,
      createdAtInSeconds: createdSec,
      updatedAtInSeconds: updatedSec,
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(createdSec);
    expect(result.updatedAtInSeconds).toBe(updatedSec);
  });

  it("defaults createdAtInSeconds to 0 when not provided or invalid", () => {
    const raw = {
      id: 2,
      updatedAtInSeconds: 1718542800,
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(0);
  });

  it("defaults updatedAtInSeconds to 0 when not provided or invalid", () => {
    const raw = {
      id: 3,
      createdAtInSeconds: 1718456400,
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.updatedAtInSeconds).toBe(0);
  });

  it("defaults both timestamps to 0 when both are missing", () => {
    const raw = { id: 4, files: [] };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(0);
    expect(result.updatedAtInSeconds).toBe(0);
  });

  it("defaults files to an empty array when files is null", () => {
    const raw = { id: 5, files: null };
    const result = normalizeTemplate(raw);
    expect(result.files).toEqual([]);
  });

  it("defaults files to an empty array when files is undefined", () => {
    const raw = { id: 6 };
    const result = normalizeTemplate(raw);
    expect(result.files).toEqual([]);
  });

  it("preserves existing files array", () => {
    const files = [
      { fileType: "bpmn" as const, fileName: "diagram.bpmn" },
      { fileType: "json" as const, fileName: "form.json" },
    ];
    const raw = { id: 7, files };
    const result = normalizeTemplate(raw);
    expect(result.files).toEqual(files);
  });

  it("preserves all pass-through fields", () => {
    const raw = {
      id: 10,
      templateKey: "my-template",
      version: "V1",
      name: "My Template",
      description: "A test template",
      tags: ["tag1", "tag2"],
      category: "workflow",
      tenantId: "tenant-a",
      visibility: "PRIVATE",
      isPublished: false,
      status: "draft",
      createdBy: "user1",
      modifiedBy: "user2",
      files: [],
      createdAtInSeconds: 1735689600,
      updatedAtInSeconds: 1735776000,
    };
    const result = normalizeTemplate(raw);
    expect(result.id).toBe(10);
    expect(result.templateKey).toBe("my-template");
    expect(result.version).toBe("V1");
    expect(result.name).toBe("My Template");
    expect(result.description).toBe("A test template");
    expect(result.tags).toEqual(["tag1", "tag2"]);
    expect(result.category).toBe("workflow");
    expect(result.tenantId).toBe("tenant-a");
    expect(result.visibility).toBe("PRIVATE");
    expect(result.isPublished).toBe(false);
    expect(result.status).toBe("draft");
    expect(result.createdBy).toBe("user1");
    expect(result.modifiedBy).toBe("user2");
    expect(result.createdAtInSeconds).toBe(1735689600);
    expect(result.updatedAtInSeconds).toBe(1735776000);
  });

  it("handles a completely empty object gracefully", () => {
    const raw = {};
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(0);
    expect(result.updatedAtInSeconds).toBe(0);
    expect(result.files).toEqual([]);
  });

  it("defaults to 0 when createdAtInSeconds is missing or not a positive number", () => {
    const raw = {
      id: 11,
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(0);
    expect(result.updatedAtInSeconds).toBe(0);
  });

  it("derives createdAtInSeconds from createdAt ISO string when createdAtInSeconds not provided", () => {
    const raw = {
      id: 12,
      createdAt: "2025-06-15T10:30:00.000Z",
      updatedAt: "2025-06-16T12:00:00.000Z",
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(Math.floor(new Date("2025-06-15T10:30:00.000Z").getTime() / 1000));
    expect(result.updatedAtInSeconds).toBe(Math.floor(new Date("2025-06-16T12:00:00.000Z").getTime() / 1000));
  });

  it("prefers createdAtInSeconds/updatedAtInSeconds over ISO strings when both present", () => {
    const raw = {
      id: 13,
      createdAt: "2020-01-01T00:00:00.000Z",
      updatedAt: "2020-01-02T00:00:00.000Z",
      createdAtInSeconds: 1735689600,
      updatedAtInSeconds: 1735776000,
      files: [],
    };
    const result = normalizeTemplate(raw);
    expect(result.createdAtInSeconds).toBe(1735689600);
    expect(result.updatedAtInSeconds).toBe(1735776000);
  });
});

describe("sortFilesWithPrimaryFirst", () => {
  it("moves the primary file to the front of the array", () => {
    const files = [
      { name: "test.bpmn" },
      { name: "form.json" },
      { name: "primary.bpmn" },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "primary.bpmn");
    expect(sorted[0].name).toBe("primary.bpmn");
    expect(sorted).toHaveLength(3);
  });

  it("preserves order when primary is already first", () => {
    const files = [
      { name: "primary.bpmn" },
      { name: "test.bpmn" },
      { name: "form.json" },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "primary.bpmn");
    expect(sorted[0].name).toBe("primary.bpmn");
    expect(sorted[1].name).toBe("test.bpmn");
    expect(sorted[2].name).toBe("form.json");
  });

  it("returns files unchanged when primaryFileName is empty", () => {
    const files = [
      { name: "b.bpmn" },
      { name: "a.bpmn" },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "");
    expect(sorted[0].name).toBe("b.bpmn");
    expect(sorted[1].name).toBe("a.bpmn");
  });

  it("returns files unchanged when primaryFileName does not match any file", () => {
    const files = [
      { name: "test.bpmn" },
      { name: "form.json" },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "nonexistent.bpmn");
    expect(sorted[0].name).toBe("test.bpmn");
    expect(sorted[1].name).toBe("form.json");
  });

  it("does not mutate the original array", () => {
    const files = [
      { name: "b.bpmn" },
      { name: "a.bpmn" },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "a.bpmn");
    expect(sorted[0].name).toBe("a.bpmn");
    // Original should be unchanged
    expect(files[0].name).toBe("b.bpmn");
  });

  it("handles a single-element array", () => {
    const files = [{ name: "only.bpmn" }];
    const sorted = sortFilesWithPrimaryFirst(files, "only.bpmn");
    expect(sorted).toHaveLength(1);
    expect(sorted[0].name).toBe("only.bpmn");
  });

  it("handles an empty array", () => {
    const sorted = sortFilesWithPrimaryFirst([], "primary.bpmn");
    expect(sorted).toEqual([]);
  });

  it("works with objects that have additional properties", () => {
    const files = [
      { name: "test.bpmn", content: new Blob(["x"]) },
      { name: "primary.bpmn", content: new Blob(["y"]) },
    ];
    const sorted = sortFilesWithPrimaryFirst(files, "primary.bpmn");
    expect(sorted[0].name).toBe("primary.bpmn");
    expect(sorted[0].content).toBeDefined();
  });
});
