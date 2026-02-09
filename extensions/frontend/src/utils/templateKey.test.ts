import { describe, it, expect } from "vitest";
import { nameToTemplateKey } from "./templateKey";

describe("nameToTemplateKey", () => {
  it("converts a simple name to a slug", () => {
    expect(nameToTemplateKey("My Template")).toBe("my-template");
  });

  it("trims leading and trailing whitespace", () => {
    expect(nameToTemplateKey("  hello  ")).toBe("hello");
  });

  it("collapses multiple spaces into a single hyphen", () => {
    expect(nameToTemplateKey("a   b")).toBe("a-b");
  });

  it("strips special characters", () => {
    expect(nameToTemplateKey("test@#$%")).toBe("test");
  });

  it("preserves underscores", () => {
    expect(nameToTemplateKey("my_template")).toBe("my_template");
  });

  it("returns empty string for all-special-character input", () => {
    expect(nameToTemplateKey("@#$%")).toBe("");
  });

  it("returns empty string for empty input", () => {
    expect(nameToTemplateKey("")).toBe("");
  });

  it("returns empty string for whitespace-only input", () => {
    expect(nameToTemplateKey("   ")).toBe("");
  });

  it("strips leading and trailing hyphens from the result", () => {
    expect(nameToTemplateKey("-hello-")).toBe("hello");
  });

  it("strips unicode characters that are not a-z, 0-9, hyphen, or underscore", () => {
    expect(nameToTemplateKey("caf\u00e9")).toBe("caf");
  });

  it("handles mixed case and numbers", () => {
    expect(nameToTemplateKey("Approval Workflow V2")).toBe(
      "approval-workflow-v2"
    );
  });

  it("collapses repeated hyphens from special chars between words", () => {
    expect(nameToTemplateKey("a--b--c")).toBe("a-b-c");
  });

  it("handles a name with only numbers", () => {
    expect(nameToTemplateKey("123")).toBe("123");
  });

  it("handles a name with hyphens, underscores, and spaces", () => {
    expect(nameToTemplateKey("my - cool_template name")).toBe(
      "my-cool_template-name"
    );
  });

  it("handles tab characters as whitespace", () => {
    expect(nameToTemplateKey("a\tb")).toBe("a-b");
  });
});
