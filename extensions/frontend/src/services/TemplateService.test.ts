import { describe, it, expect, vi, beforeEach } from "vitest";
import HttpService from "@spiffworkflow-frontend/services/HttpService";
import TemplateService from "./TemplateService";

vi.mock("@spiffworkflow-frontend/services/HttpService", () => ({
  default: {
    makeCallToBackend: vi.fn(),
  },
}));

describe("TemplateService", () => {
  beforeEach(() => {
    vi.mocked(HttpService.makeCallToBackend).mockReset();
  });

  describe("createTemplate", () => {
    const sampleBpmnXml = '<?xml version="1.0"?><bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL"/>';

    it("calls makeCallToBackend with path, POST, BPMN body, and required headers", async () => {
      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.({
          id: 1,
          templateKey: "test-key",
          name: "Test Template",
          version: "V1",
          visibility: "PRIVATE",
        } as any);
      });

      await TemplateService.createTemplate(sampleBpmnXml, {
        template_key: "test-key",
        name: "Test Template",
      });

      expect(HttpService.makeCallToBackend).toHaveBeenCalledTimes(1);
      const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
      expect(call.path).toBe("/v1.0/m8flow/templates");
      expect(call.httpMethod).toBe("POST");
      expect(call.postBody).toBe(sampleBpmnXml);
      expect(call.extraHeaders).toEqual(
        expect.objectContaining({
          "Content-Type": "application/xml",
          "X-Template-Key": "test-key",
          "X-Template-Name": "Test Template",
        })
      );
    });

    it("includes optional visibility and other metadata in headers when provided", async () => {
      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.({} as any);
      });

      await TemplateService.createTemplate(sampleBpmnXml, {
        template_key: "my-key",
        name: "My Template",
        description: "A description",
        category: "Approval",
        tags: ["tag1", "tag2"],
        visibility: "TENANT",
      });

      const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0];
      expect(call.extraHeaders).toEqual(
        expect.objectContaining({
          "Content-Type": "application/xml",
          "X-Template-Key": "my-key",
          "X-Template-Name": "My Template",
          "X-Template-Description": "A description",
          "X-Template-Category": "Approval",
          "X-Template-Tags": JSON.stringify(["tag1", "tag2"]),
          "X-Template-Visibility": "TENANT",
        })
      );
    });

    it("rejects when template_key or name is missing", async () => {
      await expect(
        TemplateService.createTemplate(sampleBpmnXml, {
          template_key: "",
          name: "Test",
        })
      ).rejects.toThrow("Template key and name are required");

      await expect(
        TemplateService.createTemplate(sampleBpmnXml, {
          template_key: "key",
          name: "",
        })
      ).rejects.toThrow("Template key and name are required");

      expect(HttpService.makeCallToBackend).not.toHaveBeenCalled();
    });
  });
});
