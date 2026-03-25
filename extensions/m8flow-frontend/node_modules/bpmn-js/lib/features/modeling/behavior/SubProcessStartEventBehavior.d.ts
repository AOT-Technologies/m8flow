/**
 * Add start event replacing element with expanded sub process.
 *
 */
export default class SubProcessStartEventBehavior extends CommandInterceptor {
    /**
     * @param injector
     * @param modeling
     */
    constructor(injector: Injector, modeling: Modeling);
}

type Injector = import('didi').Injector;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
