export default class AssociationBehavior extends CommandInterceptor {
    /**
     * @param injector
     * @param modeling
     */
    constructor(injector: Injector, modeling: Modeling);
}

type Injector = import('didi').Injector;
type Modeling = import('../Modeling').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
