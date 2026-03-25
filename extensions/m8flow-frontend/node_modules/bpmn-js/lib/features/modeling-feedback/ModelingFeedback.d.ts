export default class ModelingFeedback {
    static $inject: string[];
    /**
     * @param eventBus
     * @param tooltips
     * @param translate
     */
    constructor(eventBus: EventBus, tooltips: Tooltips, translate: Translate);
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
type Tooltips = import('diagram-js/lib/features/tooltips/Tooltips').default;
export type Translate = typeof import("diagram-js/lib/i18n/translate/translate").default;
