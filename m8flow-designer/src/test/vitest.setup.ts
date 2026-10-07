import '@testing-library/jest-dom';

// React Router creates a Request during memory-router redirects. Node's
// undici Request rejects jsdom's cross-realm AbortSignal, even though the
// redirect itself does not depend on cancellation in these tests. Strip the
// cross-realm signal in the test environment so route-guard tests exercise
// navigation rather than the host runtime's fetch implementation.
if (typeof globalThis.Request !== 'undefined') {
  const NativeRequest = globalThis.Request;
  class TestRequest extends NativeRequest {
    constructor(input: RequestInfo | URL, init?: RequestInit) {
      super(input, init ? { ...init, signal: undefined } : undefined);
    }
  }
  globalThis.Request = TestRequest;
}

// jsdom doesn't implement these — without them, mounting any Radix primitive
// that positions a floating panel (Select, DropdownMenu, Popover, Tooltip)
// throws ("ResizeObserver is not defined") or silently fails to open
// ("target.hasPointerCapture is not a function") in tests.
if (typeof globalThis.ResizeObserver === 'undefined') {
  class ResizeObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver;
}

// dmn-js/bpmn-js properties panels observe sticky headers with an
// IntersectionObserver — unstubbed, mounting either canvas rejects with
// "IntersectionObserver is not defined" from inside preact's render.
if (typeof globalThis.IntersectionObserver === 'undefined') {
  class IntersectionObserverStub {
    observe() {}
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  globalThis.IntersectionObserver = IntersectionObserverStub as unknown as typeof IntersectionObserver;
}

if (typeof Element !== 'undefined') {
  Element.prototype.hasPointerCapture ??= () => false;
  Element.prototype.setPointerCapture ??= () => {};
  Element.prototype.releasePointerCapture ??= () => {};
  Element.prototype.scrollIntoView ??= () => {};
}
