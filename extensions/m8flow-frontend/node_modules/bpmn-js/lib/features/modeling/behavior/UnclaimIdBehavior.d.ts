/**
 * Unclaims model IDs on element deletion.
 *
 */
export default class UnclaimIdBehavior extends CommandInterceptor {
    /**
     * @param canvas
     * @param injector
     * @param moddle
     * @param modeling
     */
    constructor(canvas: Canvas, injector: Injector, moddle: Moddle, modeling: Modeling);
}

type Canvas = import('diagram-js/lib/core/Canvas').default;
type Injector = import('didi').Injector;
type Modeling = import('../Modeling').default;
type Moddle = import('../../../model/Types').Moddle;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
