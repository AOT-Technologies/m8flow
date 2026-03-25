/**
 * A viewer with mouse and keyboard navigation features.
 *
 *
 * @extends Viewer<ServiceMap>
 *
 */
export default class NavigatedViewer<ServiceMap = null> extends Viewer<ServiceMap> {}

type BaseViewerOptions = import('./BaseViewer').BaseViewerOptions;
import Viewer from './Viewer';
