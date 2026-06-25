import { describe, it, expect } from "vitest";
import {
  isValidTemplateName,
  nameToTemplateKey,
  TEMPLATE_NAME_MAX_LENGTH,
} from "./templateKey";

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

describe("isValidTemplateName", () => {
  it("accepts letters, numbers, spaces, hyphens and underscores", () => {
    expect(isValidTemplateName("My Template_v2")).toBe(true);
    expect(isValidTemplateName("approval-flow 2024")).toBe(true);
    expect(isValidTemplateName("123")).toBe(true);
  });

  it("trims before validating", () => {
    expect(isValidTemplateName("  My Template  ")).toBe(true);
  });

  it("rejects other special characters", () => {
    expect(isValidTemplateName("Test@Template")).toBe(false);
    expect(isValidTemplateName("report/final")).toBe(false);
    expect(isValidTemplateName("price#1")).toBe(false);
    expect(isValidTemplateName("a.b")).toBe(false);
  });

  it("rejects accented/unicode letters", () => {
    expect(isValidTemplateName("café")).toBe(false);
    expect(isValidTemplateName("价格")).toBe(false);
  });

  it("rejects an empty or whitespace-only name", () => {
    expect(isValidTemplateName("")).toBe(false);
    expect(isValidTemplateName("   ")).toBe(false);
  });
});

describe("TEMPLATE_NAME_MAX_LENGTH", () => {
  it("is 100", () => {
    expect(TEMPLATE_NAME_MAX_LENGTH).toBe(100);
  });
});
