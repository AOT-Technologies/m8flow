import CommandInterceptor from 'diagram-js/lib/command/CommandInterceptor';

import { is } from 'bpmn-js/lib/util/ModelUtil';

const LOW_PRIORITY = 250;

/**
 * Camunda-specific behavior ensuring `isExecutable` is kept after deleting
 * the last participant.
 */
export default class DeleteParticipantBehaviour extends CommandInterceptor {
  constructor(eventBus, canvas, modeling) {
    super(eventBus);

    this.postExecuted('shape.delete', LOW_PRIORITY, function(context) {
      const {
        collaborationRoot,
        shape
      } = context;

      const newRoot = canvas.getRootElement();

      if (is(shape, 'bpmn:Participant') &&
          collaborationRoot &&
          !collaborationRoot.businessObject.get('participants').length &&
          is(newRoot, 'bpmn:Process')) {

        const oldProcessBusinessObject = shape.businessObject.get('processRef');

        if (!oldProcessBusinessObject) {
          return;
        }

        modeling.updateProperties(newRoot, { isExecutable: oldProcessBusinessObject.get('isExecutable') });
      }

    }, true);
  }
}

DeleteParticipantBehaviour.$inject = [
  'eventBus',
  'canvas',
  'modeling'
];