/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BACKEND_BASE_URL?: string;
  readonly VITE_MCP_SERVER_URL?: string;
  readonly VITE_M8FLOW_CELERY_FLOWER_URL?: string;
  readonly VITE_M8FLOW_NATS_UI_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

declare module 'dmn-js/lib/Viewer' {
  const DmnViewer: any;
  export default DmnViewer;
}
