/**
 * Service Task ↔ connector-profile binding. Pure functions so the Config
 * tab picker and the Parameters-tab hide list can be tested without Preact
 * or a bpmn-js instance.
 *
 * Parameter values are Python expressions, so a literal profile name is
 * quoted (`"http-prod"`). The host pops `m8flow_profile` before the proxy.
 */

export const PROFILE_PARAMETER_ID = 'm8flow_profile';
export const PARAMETERS_TYPE = 'spiffworkflow:Parameters';
export const PARAMETER_TYPE = 'spiffworkflow:Parameter';

/** HTTP profile-supplied params. Hidden on Parameters when a profile is set. */
export const HTTP_PROFILE_FIELD_IDS = ['basic_auth_username', 'basic_auth_password'] as const;

export type OperatorParameter = {
  id: string;
  type?: string;
  value?: string;
};

export type ServiceTaskOperator = {
  id?: string;
  parameterList?: { parameters?: OperatorParameter[] };
};

export type ConnectorProfileOption = {
  profile_name: string;
  display_name: string;
};

export function connectorTypeForOperator(operatorId: string): string {
  if (!operatorId) {
    return '';
  }
  const slash = operatorId.indexOf('/');
  return slash === -1 ? operatorId : operatorId.slice(0, slash);
}

export function quoteProfileName(name: string): string {
  return JSON.stringify(name);
}

/** Unquoted URLs are not valid Python; Spiff evaluates parameter values. */
const URLISH = /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//;

export function quoteStringParameterIfLiteral(raw: string): string {
  const trimmed = raw.trim();
  if (!URLISH.test(trimmed)) {
    return raw;
  }
  try {
    const parsed = JSON.parse(trimmed) as unknown;
    if (typeof parsed === 'string') {
      return trimmed;
    }
  } catch {
    // not already a quoted JSON string
  }
  return JSON.stringify(trimmed);
}

export function displayStringParameter(raw: unknown): string {
  if (typeof raw !== 'string') {
    return '';
  }
  try {
    const parsed = JSON.parse(raw) as unknown;
    if (typeof parsed === 'string' && URLISH.test(parsed)) {
      return parsed;
    }
  } catch {
    // show the stored expression
  }
  return raw;
}

export function unquoteProfileName(rawValue: unknown): string {
  if (typeof rawValue !== 'string') {
    return '';
  }
  try {
    const parsed = JSON.parse(rawValue.trim()) as unknown;
    return typeof parsed === 'string' ? parsed : '';
  } catch {
    return '';
  }
}

export function parameterById(
  operator: ServiceTaskOperator | null | undefined,
  id: string,
): OperatorParameter | null {
  const parameters = operator?.parameterList?.parameters;
  if (!Array.isArray(parameters)) {
    return null;
  }
  return parameters.find((parameter) => parameter.id === id) ?? null;
}

export function selectedProfileName(operator: ServiceTaskOperator | null | undefined): string {
  return unquoteProfileName(parameterById(operator, PROFILE_PARAMETER_ID)?.value);
}

export function hiddenParameterIds(
  profileSelected: boolean,
  extraFieldIds: readonly string[] = HTTP_PROFILE_FIELD_IDS,
): Set<string> {
  const hidden = new Set<string>([PROFILE_PARAMETER_ID]);
  if (profileSelected) {
    for (const id of extraFieldIds) {
      hidden.add(id);
    }
  }
  return hidden;
}

export function visibleParameterItems<T extends { label: string }>(
  items: T[],
  hidden: Set<string>,
): T[] {
  return items.filter((item) => !hidden.has(item.label));
}

type ModdleLike = {
  create(type: string): { parameters?: OperatorParameter[]; id?: string; type?: string; value?: string };
};

function ensureParameterList(operator: ServiceTaskOperator, moddle: ModdleLike): OperatorParameter[] {
  if (!operator.parameterList) {
    const parameterList = moddle.create(PARAMETERS_TYPE) as { parameters: OperatorParameter[] };
    parameterList.parameters = [];
    operator.parameterList = parameterList;
  }
  const parameters = operator.parameterList.parameters;
  if (!Array.isArray(parameters)) {
    operator.parameterList.parameters = [];
    return operator.parameterList.parameters;
  }
  return parameters;
}

export function writeProfileParameter(
  operator: ServiceTaskOperator,
  moddle: ModdleLike,
  value: string,
): void {
  const parameters = ensureParameterList(operator, moddle);
  const existing = parameterById(operator, PROFILE_PARAMETER_ID);

  if (!value) {
    if (existing) {
      parameters.splice(parameters.indexOf(existing), 1);
    }
    return;
  }

  if (existing) {
    existing.value = quoteProfileName(value);
    return;
  }

  const parameter = moddle.create(PARAMETER_TYPE) as OperatorParameter;
  parameter.id = PROFILE_PARAMETER_ID;
  parameter.type = 'any';
  parameter.value = quoteProfileName(value);
  parameters.push(parameter);
}

export function blankSuppliedParameters(
  operator: ServiceTaskOperator,
  fieldIds: readonly string[],
): void {
  const parameters = operator.parameterList?.parameters;
  if (!Array.isArray(parameters)) {
    return;
  }
  const supplied = new Set(fieldIds);
  for (const parameter of parameters) {
    if (supplied.has(parameter.id)) {
      parameter.value = undefined;
    }
  }
}

/**
 * Remember the last profile chosen per element so an operator change that
 * rebuilds parameterList (vendor dropdown) can restore m8flow_profile when
 * the new operator is still the same connector family.
 */
export function createProfileMemory() {
  const lastConnectorByElement = new Map<string, string>();
  const lastProfileByElement = new Map<string, string>();

  return {
    remember(elementId: string, connectorType: string, profileName: string) {
      lastConnectorByElement.set(elementId, connectorType);
      lastProfileByElement.set(elementId, profileName);
    },
    forget(elementId: string) {
      lastConnectorByElement.delete(elementId);
      lastProfileByElement.delete(elementId);
    },
    reconcile(
      elementId: string,
      operator: ServiceTaskOperator,
      connectorType: string,
      moddle: ModdleLike,
      fieldIds: readonly string[],
    ): string {
      const current = selectedProfileName(operator);
      if (current) {
        lastConnectorByElement.set(elementId, connectorType);
        lastProfileByElement.set(elementId, current);
        return current;
      }
      const remembered = lastConnectorByElement.get(elementId);
      if (!remembered) {
        return '';
      }
      if (remembered !== connectorType) {
        lastConnectorByElement.delete(elementId);
        lastProfileByElement.delete(elementId);
        return '';
      }
      const selected = lastProfileByElement.get(elementId);
      if (!selected) {
        return '';
      }
      writeProfileParameter(operator, moddle, selected);
      blankSuppliedParameters(operator, fieldIds);
      return selected;
    },
    reset() {
      lastConnectorByElement.clear();
      lastProfileByElement.clear();
    },
  };
}
