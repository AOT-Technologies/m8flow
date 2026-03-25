/**
 * A component that makes sure that each created or updated
 * Pool and Lane is assigned an isHorizontal property set to true.
 *
 */
export default class IsHorizontalFix extends CommandInterceptor {
}

type EventBus = import('diagram-js/lib/core/EventBus').default;
import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';
