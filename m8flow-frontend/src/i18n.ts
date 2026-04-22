import i18n from '@spiffworkflow-frontend/i18n';

import baseEnUS from '@spiffworkflow-frontend/locales/en_us/translation.json';
import enUS from './locales/en_us/translation.json';

import basePtBR from '@spiffworkflow-frontend/locales/pt_br/translation.json';
import ptBR from './locales/pt_br/translation.json';

import baseEs from '@spiffworkflow-frontend/locales/es/translation.json';
import es from './locales/es/translation.json';

import baseDe from '@spiffworkflow-frontend/locales/de/translation.json';
import de from './locales/de/translation.json';

import baseFi from '@spiffworkflow-frontend/locales/fi/translation.json';
import fi from './locales/fi/translation.json';

import basePtPT from '@spiffworkflow-frontend/locales/pt_pt/translation.json';
import ptPT from './locales/pt_pt/translation.json';

import baseCsCZ from '@spiffworkflow-frontend/locales/cs_cz/translation.json';
import csCZ from './locales/cs_cz/translation.json';

import baseZhCN from '@spiffworkflow-frontend/locales/zh_cn/translation.json';
import zhCN from './locales/zh_cn/translation.json';

import baseFrFR from '@spiffworkflow-frontend/locales/fr_fr/translation.json';
import frFR from './locales/fr_fr/translation.json';

// Add the extension-specific resources to the existing i18n instance
// We manually merge the base translations with our extension translations
// to ensure no upstream translations are lost.
i18n.addResourceBundle('en-US', 'translation', { ...baseEnUS, ...enUS }, true, true);
i18n.addResourceBundle('pt-BR', 'translation', { ...basePtBR, ...ptBR }, true, true);
i18n.addResourceBundle('es', 'translation', { ...baseEs, ...es }, true, true);
i18n.addResourceBundle('de', 'translation', { ...baseDe, ...de }, true, true);
i18n.addResourceBundle('fi', 'translation', { ...baseFi, ...fi }, true, true);
i18n.addResourceBundle('pt-PT', 'translation', { ...basePtPT, ...ptPT }, true, true);
i18n.addResourceBundle('cs-CZ', 'translation', { ...baseCsCZ, ...csCZ }, true, true);
i18n.addResourceBundle('zh-CN', 'translation', { ...baseZhCN, ...zhCN }, true, true);
i18n.addResourceBundle('fr-FR', 'translation', { ...baseFrFR, ...frFR }, true, true);

export default i18n;
