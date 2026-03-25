import CopyPasteBehavior from './CopyPasteBehavior';
import CopyPasteRootElementBehavior from './CopyPasteRootElementBehavior';
import DeleteErrorEventDefinitionBehavior from './DeleteErrorEventDefinitionBehavior';
import DeleteParticipantBehaviour from '../shared/DeleteParticipantBehaviour';
import DeleteRetryTimeCycleBehavior from './DeleteRetryTimeCycleBehavior';
import OrderExtensionElementsBehavior from './OrderExtensionElementsBehavior';
import RemoveInitiatorBehaviour from './RemoveInitiatorBehaviour';
import RemoveVariableEventBehaviour from './RemoveVariableEventBehaviour';
import UpdateCamundaExclusiveBehavior from './UpdateCamundaExclusiveBehavior';
import UpdateInputOutputBehavior from './UpdateInputOutputBehavior';
import UpdateResultVariableBehavior from './UpdateResultVariableBehavior';
import UserTaskFormsBehavior from './UserTaskFormsBehavior';
import UserTaskGeneratedFormsBehavior from './UserTaskGeneratedFormsBehavior';

export default {
  __init__: [
    'copyPasteBehavior',
    'copyPasteRootElementBehavior',
    'deleteErrorEventDefinitionBehavior',
    'deleteParticipantBehaviour',
    'deleteRetryTimeCycleBehavior',
    'orderExtensionElementsBehavior',
    'removeInitiatorBehaviour',
    'removeVariableEventBehaviour',
    'updateCamundaExclusiveBehavior',
    'updateResultVariableBehavior',
    'updateInputOutputBehavior',
    'userTaskFormsBehavior',
    'userTaskGeneratedFormsBehavior'
  ],
  copyPasteBehavior: [ 'type', CopyPasteBehavior ],
  copyPasteRootElementBehavior: [ 'type', CopyPasteRootElementBehavior ],
  deleteErrorEventDefinitionBehavior: [ 'type', DeleteErrorEventDefinitionBehavior ],
  deleteParticipantBehaviour: [ 'type', DeleteParticipantBehaviour ],
  deleteRetryTimeCycleBehavior: [ 'type', DeleteRetryTimeCycleBehavior ],
  orderExtensionElementsBehavior: [ 'type', OrderExtensionElementsBehavior ],
  removeInitiatorBehaviour: [ 'type', RemoveInitiatorBehaviour ],
  removeVariableEventBehaviour: [ 'type', RemoveVariableEventBehaviour ],
  updateCamundaExclusiveBehavior: [ 'type', UpdateCamundaExclusiveBehavior ],
  updateResultVariableBehavior: [ 'type', UpdateResultVariableBehavior ],
  updateInputOutputBehavior: [ 'type', UpdateInputOutputBehavior ],
  userTaskFormsBehavior: [ 'type', UserTaskFormsBehavior ],
  userTaskGeneratedFormsBehavior: [ 'type', UserTaskGeneratedFormsBehavior ]
};
