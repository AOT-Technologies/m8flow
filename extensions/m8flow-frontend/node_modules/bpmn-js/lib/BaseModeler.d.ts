/**
 * A base modeler for BPMN 2.0 diagrams.
 *
 * See {@link bpmn-js/lib/Modeler} for a fully-featured modeler.
 *
 *
 * @extends BaseViewer<ServiceMap>
 *
 */
export default class BaseModeler<ServiceMap = null> extends BaseViewer<ServiceMap> {}

type BaseViewerOptions = import('./BaseViewer').BaseViewerOptions;
type ModdleElementsById = import('./BaseViewer').ModdleElementsById;
type ModdleElement = import('./model/Types').ModdleElement;
import BaseViewer from './BaseViewer';
