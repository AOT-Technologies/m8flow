import CleanUpAdHocSubProcessBehavior from './CleanUpAdHocSubProcessBehavior';
import CleanUpBusinessRuleTaskBehavior from './CleanUpBusinessRuleTaskBehavior';
import CleanUpEndEventBehavior from './CleanUpEndEventBehavior';
import CleanUpExecutionListenersBehavior from './CleanUpExecutionListenersBehavior';
import CleanUpMessageRefBehavior from './CleanUpMessageRefBehavior';
import CleanUpTaskListenersBehavior from './CleanUpTaskListenersBehavior';
import CleanUpSubscriptionBehavior from './CleanUpSubscriptionBehavior';
import CleanUpTimerExpressionBehavior from './CleanUpTimerExpressionBehavior';
import CopyPasteBehavior from './CopyPasteBehavior';
import CreateZeebeCallActivityBehavior from './CreateZeebeCallActivityBehavior';
import CreateZeebeUserTaskBehavior from './CreateZeebeUserTaskBehavior';
import DeleteParticipantBehaviour from '../shared/DeleteParticipantBehaviour';
import FormsBehavior from './FormsBehavior';
import RemoveAssignmentDefinitionBehavior from './RemoveAssignmentDefinitionBehavior';
import RemoveTaskScheduleBehavior from './RemoveTaskScheduleBehavior';
import CallActivityVariablesPropagationBehavior from './CallActivityVariablesPropagationBehavior';
import VersionTagBehavior from './VersionTagBehavior';

export default {
  __init__: [
    'callActivityVariablesPropagationBehavior',
    'cleanUpAdHocSubProcessBehavior',
    'cleanUpBusinessRuleTaskBehavior',
    'cleanUpEndEventBehavior',
    'cleanUpExecutionListenersBehavior',
    'cleanUpMessageRefBehavior',
    'cleanUpTaskListenersBehavior',
    'cleanUpSubscriptionBehavior',
    'cleanUpTimerExpressionBehavior',
    'copyPasteBehavior',
    'createZeebeCallActivityBehavior',
    'createZeebeUserTaskBehavior',
    'deleteParticipantBehaviour',
    'formsBehavior',
    'removeAssignmentDefinitionBehavior',
    'removeTaskScheduleBehavior',
    'versionTagBehavior'
  ],
  callActivityVariablesPropagationBehavior: [ 'type', CallActivityVariablesPropagationBehavior ],
  cleanUpAdHocSubProcessBehavior: [ 'type', CleanUpAdHocSubProcessBehavior ],
  cleanUpBusinessRuleTaskBehavior: [ 'type', CleanUpBusinessRuleTaskBehavior ],
  cleanUpEndEventBehavior: [ 'type', CleanUpEndEventBehavior ],
  cleanUpExecutionListenersBehavior: [ 'type', CleanUpExecutionListenersBehavior ],
  cleanUpMessageRefBehavior: [ 'type', CleanUpMessageRefBehavior ],
  cleanUpTaskListenersBehavior: [ 'type', CleanUpTaskListenersBehavior ],
  cleanUpSubscriptionBehavior: [ 'type', CleanUpSubscriptionBehavior ],
  cleanUpTimerExpressionBehavior: [ 'type', CleanUpTimerExpressionBehavior ],
  copyPasteBehavior: [ 'type', CopyPasteBehavior ],
  createZeebeCallActivityBehavior: [ 'type', CreateZeebeCallActivityBehavior ],
  createZeebeUserTaskBehavior: [ 'type', CreateZeebeUserTaskBehavior ],
  deleteParticipantBehaviour: [ 'type', DeleteParticipantBehaviour ],
  formsBehavior: [ 'type', FormsBehavior ],
  removeAssignmentDefinitionBehavior: [ 'type', RemoveAssignmentDefinitionBehavior ],
  removeTaskScheduleBehavior: [ 'type', RemoveTaskScheduleBehavior ],
  versionTagBehavior: [ 'type', VersionTagBehavior ]
};
