import { describe, it, expect, vi, beforeEach } from "vitest";
import HttpService from "./HttpService";
import TemplateService from "./TemplateService";

vi.mock("./HttpService", () => ({
  default: {
    makeCallToBackend: vi.fn(),
    getBasicHeaders: vi.fn().mockReturnValue({}),
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

  describe("deleteTemplate", () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
      fetchMock.mockClear();
      vi.stubGlobal("fetch", fetchMock);
    });

    it("sends DELETE to correct URL and resolves when response is ok", async () => {
      fetchMock.mockResolvedValue({ ok: true });

      await expect(TemplateService.deleteTemplate(7)).resolves.toBeUndefined();

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/templates/7"),
        expect.objectContaining({
          method: "DELETE",
          credentials: "include",
        })
      );
    });

    it("rejects with error when response is not ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });

      await expect(TemplateService.deleteTemplate(7)).rejects.toThrow("Delete failed");

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  describe("updateTemplateFile", () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
      fetchMock.mockClear();
      vi.stubGlobal("fetch", fetchMock);
    });

    it("sends PUT request and returns parsed template on success", async () => {
      const mockTemplateResponse = {
        id: 5,
        template_key: "test-key",
        name: "Test Template",
        version: "V2",
        visibility: "PRIVATE",
        is_published: false,
        files: [{ file_type: "json", file_name: "form.json" }],
        created_at_in_seconds: 1700000000,
        updated_at_in_seconds: 1700000001,
      };

      fetchMock.mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockTemplateResponse),
      });

      const result = await TemplateService.updateTemplateFile(
        3,
        "form.json",
        '{"updated": true}',
        "application/json"
      );

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/templates/3/files/form.json"),
        expect.objectContaining({
          method: "PUT",
          credentials: "include",
          body: '{"updated": true}',
        })
      );

      expect(result.id).toBe(5);
      expect(result.version).toBe("V2");
      expect(result.templateKey).toBe("test-key");
    });

    it("rejects with error when response is not ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });

      await expect(
        TemplateService.updateTemplateFile(3, "form.json", '{"data": true}')
      ).rejects.toThrow("Update failed");

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });

  describe("deleteTemplateFile", () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
      fetchMock.mockClear();
      vi.stubGlobal("fetch", fetchMock);
    });

    it("sends DELETE request and resolves on success", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
      });

      await TemplateService.deleteTemplateFile(4, "form.json");

      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/templates/4/files/form.json"),
        expect.objectContaining({
          method: "DELETE",
          credentials: "include",
        })
      );
    });

    it("rejects with error when response is not ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });

      await expect(
        TemplateService.deleteTemplateFile(4, "form.json")
      ).rejects.toThrow("Delete failed");

      expect(fetchMock).toHaveBeenCalledTimes(1);
    });
  });
});
