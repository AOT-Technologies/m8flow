import { render, screen } from "@testing-library/react";
import { createTheme, ThemeProvider } from "@mui/material/styles";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SideNav from "./SideNav";

const theme = createTheme();

const mockCan = vi.fn();

vi.mock("@spiffworkflow-frontend/hooks/PermissionService", () => ({
  usePermissionFetcher: () => ({
    ability: { can: (...args: unknown[]) => mockCan(...(args as [string, string])) },
    permissionsLoaded: true,
  }),
}));

vi.mock("../hooks/M8flowUriListForPermissions", () => ({
  useM8flowUriListForPermissions: () => ({
    targetUris: {
      messageInstanceListPath: "/messages",
      processGroupListPath: "/process-groups",
      processInstanceListPath: "/process-instances",
      processInstanceListForMePath: "/process-instances/for-me",
      secretListPath: "/secrets",
      serviceTaskListPath: "/v1.0/service-tasks",
    },
  }),
}));

vi.mock("@spiffworkflow-frontend/helpers/appVersionInfo", () => ({
  default: () => ({}),
}));

vi.mock("@spiffworkflow-frontend/config", () => ({
  DARK_MODE_ENABLED: false,
  DOCUMENTATION_URL: "",
  SPIFF_ENVIRONMENT: "",
}));

vi.mock("../services/UserService", () => ({
  default: {
    getUserEmail: () => "user@test.com",
    getPreferredUsername: () => "user",
    getTenantName: () => "tenant",
    authenticationDisabled: () => false,
    doLogout: vi.fn(),
  },
}));

vi.mock("./SpiffLogo", () => ({
  default: () => <div data-testid="spiff-logo" />,
}));

vi.mock("@spiffworkflow-frontend/components/SpiffTooltip", () => ({
  default: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock("@spiffworkflow-frontend/components/ExtensionUxElementForDisplay", () => ({
  default: vi.fn(),
}));

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string) => key,
    i18n: {
      store: { data: { en: {} } },
      changeLanguage: vi.fn(),
      resolvedLanguage: "en-US",
    },
  }),
}));

const defaultProps = {
  isCollapsed: false,
  onToggleCollapse: vi.fn(),
  onToggleDarkMode: vi.fn(),
  isDark: false,
  additionalNavElement: null,
  setAdditionalNavElement: vi.fn(),
  extensionUxElements: null,
};

describe("SideNav", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders Connectors nav item when GET on serviceTaskListPath is allowed", () => {
    mockCan.mockImplementation((method: string, uri: string) => {
      if (method === "GET" && uri === "/v1.0/service-tasks") return true;
      return true;
    });

    render(
      <ThemeProvider theme={theme}>
        <MemoryRouter>
          <SideNav {...defaultProps} />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByTestId("nav-item-connectors")).toBeInTheDocument();
  });

  it("hides Connectors nav item when GET on serviceTaskListPath is denied", () => {
    mockCan.mockImplementation((method: string, uri: string) => {
      if (method === "GET" && uri === "/v1.0/service-tasks") return false;
      return true;
    });

    render(
      <ThemeProvider theme={theme}>
        <MemoryRouter>
          <SideNav {...defaultProps} />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.queryByTestId("nav-item-connectors")).not.toBeInTheDocument();
  });
});
