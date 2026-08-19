import { is } from 'bpmn-js/lib/util/ModelUtil';
import { SpiffExtensionTextInput } from 'bpmn-js-spiffworkflow/app/spiffworkflow/extensions/propertiesPanel/SpiffExtensionTextInput';
import HttpService from '@spiffworkflow-frontend/services/HttpService';

const LOW_PRIORITY = 500;

export const EXTERNAL_FORM_URL_PROP = 'externalFormUrl';
export const EXTERNAL_FORM_GROUP_ID = 'external_form_properties';

// Upstream "Web Form (with Json Schemas)" group; we slot ours right after it.
const JSON_SCHEMA_GROUP_ID = 'user_task_properties';

let cachedSmtpStatus = null;
let isFetchingSmtpStatus = false;

export function fetchSmtpStatus() {
  if (isFetchingSmtpStatus || cachedSmtpStatus !== null) return;
  isFetchingSmtpStatus = true;
  try {
    HttpService.makeCallToBackend({
      path: '/m8flow/notification-smtp-status',
      successCallback: (data) => {
        cachedSmtpStatus = data;
        isFetchingSmtpStatus = false;
      },
      failureCallback: () => {
        isFetchingSmtpStatus = false;
      },
    });
  } catch (_e) {
    isFetchingSmtpStatus = false;
  }
}

export function setCachedSmtpStatusForTesting(status) {
  cachedSmtpStatus = status;
}

export function getExternalFormDescription(translate) {
  fetchSmtpStatus();
  if (cachedSmtpStatus && cachedSmtpStatus.configured === false) {
    const missing = Object.entries(cachedSmtpStatus.keys_present || {})
      .filter(([, present]) => !present)
      .map(([k]) => k)
      .join(', ');
    return translate(
      `⚠️ Warning: Notification SMTP is not configured for this tenant (missing: ${missing || 'NATS_SMTP_HOST, NATS_SMTP_FROM_EMAIL'}). Assignees will not receive emails until configured in Configuration > Secrets or Connectors. When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Clear the field to disable.`
    );
  }
  if (cachedSmtpStatus && cachedSmtpStatus.configured === true) {
    return translate(
      '✓ Notification SMTP is configured. When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Clear the field to disable.'
    );
  }
  return translate(
    'When set, this user task uses an external form. Assignees are emailed a secure link to this URL. Email delivery requires tenant SMTP secrets (NATS_SMTP_HOST, NATS_SMTP_FROM_EMAIL) to be configured in Configuration > Secrets or Connectors. Clear the field to disable.'
  );
}

export default function ExternalFormPropertiesProvider(
  propertiesPanel,
  translate,
  moddle,
  commandStack
) {
  fetchSmtpStatus();
  this.getGroups = function (element) {
    return function (groups) {
      if (is(element, 'bpmn:UserTask')) {
        const group = createExternalFormGroup(
          element,
          translate,
          moddle,
          commandStack
        );
        const anchorIndex = groups.findIndex(
          (g) => g && g.id === JSON_SCHEMA_GROUP_ID
        );
        if (anchorIndex === -1) {
          groups.push(group);
        } else {
          groups.splice(anchorIndex + 1, 0, group);
        }
      }
      return groups;
    };
  };
  propertiesPanel.registerProvider(LOW_PRIORITY, this);
}

ExternalFormPropertiesProvider.$inject = [
  'propertiesPanel',
  'translate',
  'moddle',
  'commandStack',
];

function createExternalFormGroup(element, translate, moddle, commandStack) {
  return {
    id: EXTERNAL_FORM_GROUP_ID,
    label: translate('Web Form (External Form)'),
    entries: [
      {
        id: `extension_${EXTERNAL_FORM_URL_PROP}`,
        element,
        moddle,
        commandStack,
        component: SpiffExtensionTextInput,
        name: EXTERNAL_FORM_URL_PROP,
        label: translate('External form URL'),
        description: getExternalFormDescription(translate),
      },
    ],
  };
}
