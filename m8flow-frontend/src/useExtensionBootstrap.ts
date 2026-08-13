/**
 * Health probe + extension UX/CSS discovery for the app shell.
 */
import { useEffect, useState } from 'react';
import {
  ExtensionUiSchema,
  UiSchemaDisplayLocation,
  UiSchemaUxElement,
} from '@spiffworkflow-frontend/extension_ui_schema_interfaces';
import { ProcessFile, ProcessModel } from '@spiffworkflow-frontend/interfaces';
import HttpService from './services/HttpService';

type AbilityLike = {
  can: (method: string, uri: string) => boolean;
};

type BootstrapUris = {
  statusPath: string;
  extensionListPath: string;
};

type HealthPayload = {
  ok: boolean;
  can_access_frontend?: boolean;
};

type CssBundle = { content: string; id: string };

function sanitizeCssId(processModelId: string, cssFilename: string): string {
  return `${processModelId}-${cssFilename}`.replace(/[^a-zA-Z0-9]/g, '-');
}

function collectCssFromElement(
  element: UiSchemaUxElement,
  model: ProcessModel,
): CssBundle | null {
  const cssFilename = element.location_specific_configs?.css_file;
  const cssFile = model.files.find(
    (file: ProcessFile) => file.name === cssFilename,
  );
  if (!cssFile?.file_contents || !cssFilename) {
    return null;
  }
  return {
    content: cssFile.file_contents,
    id: sanitizeCssId(model.id, cssFilename),
  };
}

function parseExtensionSchema(
  model: ProcessModel,
  uiElements: UiSchemaUxElement[],
  cssBundles: CssBundle[],
): void {
  const schemaFile = model.files.find(
    (file: ProcessFile) => file.name === 'extension_uischema.json',
  );
  if (!schemaFile?.file_contents) {
    return;
  }

  try {
    const schema: ExtensionUiSchema = JSON.parse(schemaFile.file_contents);
    if (!schema?.ux_elements || schema.disabled) {
      return;
    }

    for (const element of schema.ux_elements) {
      if (element.display_location === UiSchemaDisplayLocation.css) {
        const bundle = collectCssFromElement(element, model);
        if (bundle) {
          cssBundles.push(bundle);
        }
        continue;
      }
      uiElements.push(element);
    }
  } catch {
    console.error(`Unable to get navigation items for ${model.id}`);
  }
}

function harvestExtensionPayloads(models: ProcessModel[]): {
  uiElements: UiSchemaUxElement[];
  cssBundles: CssBundle[];
} {
  const uiElements: UiSchemaUxElement[] = [];
  const cssBundles: CssBundle[] = [];
  for (const model of models) {
    parseExtensionSchema(model, uiElements, cssBundles);
  }
  return { uiElements, cssBundles };
}

export function useExtensionBootstrap({
  ability,
  permissionsLoaded,
  uris,
}: {
  ability: AbilityLike;
  permissionsLoaded: boolean;
  uris: BootstrapUris;
}) {
  const [backendIsUp, setBackendIsUp] = useState<boolean | null>(null);
  const [canAccessFrontend, setCanAccessFrontend] = useState(true);
  const [extensionUxElements, setExtensionUxElements] = useState<
    UiSchemaUxElement[] | null
  >(null);
  const [extensionCssFiles, setExtensionCssFiles] = useState<CssBundle[]>([]);

  useEffect(() => {
    const applyExtensionModels = (models: ProcessModel[]) => {
      const { uiElements, cssBundles } = harvestExtensionPayloads(models);
      if (uiElements.length > 0) {
        setExtensionUxElements(uiElements);
      }
      if (cssBundles.length > 0) {
        setExtensionCssFiles(cssBundles);
      }
    };

    const onHealthy = (payload: HealthPayload) => {
      setBackendIsUp(true);

      if (payload.can_access_frontend !== undefined) {
        setCanAccessFrontend(payload.can_access_frontend);
        if (payload.can_access_frontend === false) {
          setExtensionUxElements([]);
          return;
        }
      }

      if (!permissionsLoaded) {
        return;
      }

      const mayListExtensions = ability.can('GET', uris.extensionListPath);
      if (mayListExtensions) {
        HttpService.makeCallToBackend({
          path: uris.extensionListPath,
          successCallback: applyExtensionModels,
        });
        return;
      }

      setExtensionUxElements([]);
    };

    HttpService.makeCallToBackend({
      path: uris.statusPath,
      successCallback: onHealthy,
      failureCallback: () => setBackendIsUp(false),
    });
  }, [uris.extensionListPath, uris.statusPath, permissionsLoaded, ability]);

  return {
    backendIsUp,
    canAccessFrontend,
    extensionUxElements,
    extensionCssFiles,
  };
}
