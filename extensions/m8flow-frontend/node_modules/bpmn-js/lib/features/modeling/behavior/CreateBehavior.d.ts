export default class CreateBehavior extends CommandInterceptor {
    /**
     * @param injector
     */
    constructor(injector: Injector);
}

type Injector = import('didi').Injector;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
