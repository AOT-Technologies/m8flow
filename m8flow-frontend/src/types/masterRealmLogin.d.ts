declare module '../../../m8flow-backend/keycloak/themes/m8flow/login/resources/js/masterRealmLogin.js' {
  export function extractBackendBaseUrl(currentLocationHref: string): string | null;
  export function extractFrontendOrigin(
    currentLocationHref: string,
    referrer?: string,
  ): string | null;
  export function buildMasterRealmLoginUrl(
    currentLocationHref: string,
    referrer?: string,
    options?: {
      masterRealmIdentifier?: string;
      platformAdminPath?: string;
    },
  ): string | null;
  export function wireMasterRealmLoginButton(button?: Element | null): void;
}

declare module '../../../m8flow-backend/keycloak/themes/m8flow/login/resources/js/restartHiddenUsernameLogin.js' {
  export function restartHiddenUsernameLogin(
    marker?: Element | null,
    locationObject?: { replace(url: string): void } | null,
    storage?: {
      getItem(key: string): string | null;
      setItem(key: string, value: string): void;
      removeItem(key: string): void;
    } | null,
  ): boolean;
}
