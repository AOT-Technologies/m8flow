import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useTemplates } from "./useTemplates";
import HttpService from "../services/HttpService";

vi.mock("../services/HttpService", () => ({
  default: {
    HttpMethods: { GET: "GET" },
    makeCallToBackend: vi.fn(),
  },
}));

describe("useTemplates", () => {
  it("passes deleted filter query flags to templates list API", () => {
    vi.mocked(HttpService.makeCallToBackend).mockImplementation((opts: any) => {
      opts.successCallback?.({
        results: [],
        pagination: { count: 0, total: 0, pages: 1 },
      });
    });

    const { result } = renderHook(() => useTemplates());

    act(() => {
      result.current.fetchTemplates({
        latest_only: false,
        include_deleted: true,
        deleted_only: true,
        page: 2,
        per_page: 25,
      });
    });

    const call = vi.mocked(HttpService.makeCallToBackend).mock.calls[0][0] as any;
    expect(call.path).toContain("/v1.0/m8flow/templates?");
    expect(call.path).toContain("latest_only=false");
    expect(call.path).toContain("include_deleted=true");
    expect(call.path).toContain("deleted_only=true");
    expect(call.path).toContain("page=2");
    expect(call.path).toContain("per_page=25");
  });
});
