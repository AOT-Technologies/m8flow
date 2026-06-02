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

  describe("restoreTemplate", () => {
    const fetchMock = vi.fn();

    beforeEach(() => {
      fetchMock.mockClear();
      vi.stubGlobal("fetch", fetchMock);
    });

    it("sends POST to restore endpoint and returns parsed template", async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        json: () =>
          Promise.resolve({
            id: 7,
            templateKey: "restore-key",
            name: "Restored",
            version: "V1",
            visibility: "PRIVATE",
            files: [],
            createdAtInSeconds: 1700000000,
            updatedAtInSeconds: 1700000010,
          }),
      });

      const result = await TemplateService.restoreTemplate(7);

      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining("/templates/7/restore"),
        expect.objectContaining({
          method: "POST",
          credentials: "include",
        })
      );
      expect(result.id).toBe(7);
      expect(result.name).toBe("Restored");
    });

    it("rejects when restore response is not ok", async () => {
      fetchMock.mockResolvedValue({ ok: false });
      await expect(TemplateService.restoreTemplate(7)).rejects.toThrow("Restore failed");
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
        templateKey: "test-key",
        name: "Test Template",
        version: "V2",
        visibility: "PRIVATE",
        isPublished: false,
        files: [{ fileType: "json", fileName: "form.json" }],
        createdAtInSeconds: 1700000000,
        updatedAtInSeconds: 1700000001,
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

  // ─── API contract: snake_case → camelCase mapping ──────────────────────────
  // These tests use raw snake_case response fixtures (as the real backend returns)
  // to catch regressions in parseTemplateResponse field mapping.
  describe("updateTemplate — snake_case backend response normalization", () => {
    it("maps snake_case fields to camelCase on success", async () => {
      const snakeCaseBackendResponse = {
        id: 9,
        template_key: "snake-key",
        name: "Snake Template",
        version: "V3",
        visibility: "PUBLIC",
        is_published: true,
        is_deleted: false,
        created_by: "admin",
        created_at_in_seconds: 1700000000,
        updated_at_in_seconds: 1700000999,
        files: [],
      };

      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.(snakeCaseBackendResponse as any);
      });

      const result = await TemplateService.updateTemplate(9, { visibility: "PUBLIC" });

      // The service must surface camelCase fields regardless of backend casing
      expect(result.id).toBe(9);
      // template_key from backend should pass through (mapper spreads raw)
      // createdAtInSeconds and updatedAtInSeconds should be resolved from
      // the numeric snake_case fields via secondsFromApiOrIso
      expect(result.createdAtInSeconds).toBe(1700000000);
      expect(result.updatedAtInSeconds).toBe(1700000999);
      expect(result.files).toEqual([]);
    });

    it("derives timestamps from ISO strings when numeric seconds are absent", async () => {
      const isoResponse = {
        id: 10,
        template_key: "iso-key",
        name: "ISO Template",
        version: "V1",
        visibility: "PRIVATE",
        createdAt: "2024-03-15T12:00:00.000Z",
        updatedAt: "2024-03-16T08:30:00.000Z",
        files: [],
      };

      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.(isoResponse as any);
      });

      const result = await TemplateService.updateTemplate(10, { visibility: "PRIVATE" });

      expect(result.createdAtInSeconds).toBe(Math.floor(Date.parse("2024-03-15T12:00:00.000Z") / 1000));
      expect(result.updatedAtInSeconds).toBe(Math.floor(Date.parse("2024-03-16T08:30:00.000Z") / 1000));
    });
  });

  describe("getTemplateById — snake_case backend response normalization", () => {
    it("maps snake_case fields to normalized Template on success", async () => {
      const snakeCaseResponse = {
        id: 11,
        template_key: "get-key",
        name: "Get Template",
        version: "V2",
        visibility: "TENANT",
        is_published: false,
        is_deleted: false,
        created_at_in_seconds: 1710000000,
        updated_at_in_seconds: 1710001000,
        files: [{ file_type: "bpmn", file_name: "process.bpmn" }],
      };

      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.(snakeCaseResponse as any);
      });

      const result = await TemplateService.getTemplateById(11);

      expect(result.id).toBe(11);
      expect(result.createdAtInSeconds).toBe(1710000000);
      expect(result.updatedAtInSeconds).toBe(1710001000);
      expect(result.files).toHaveLength(1);
    });

    it("returns 0 timestamps when neither numeric seconds nor ISO strings are present", async () => {
      vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts) => {
        opts.successCallback?.({ id: 12, name: "No Dates", version: "V1", files: [] } as any);
      });

      const result = await TemplateService.getTemplateById(12);

      expect(result.createdAtInSeconds).toBe(0);
      expect(result.updatedAtInSeconds).toBe(0);
    });
  });
});
