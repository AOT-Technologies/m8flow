/**
 * Map containing SVG paths needed by BpmnRenderer
 */
export default class PathMap {
    /**
     * Contains a map of path elements
     *
     * <h1>Path definition</h1>
     * A parameterized path is defined like this:
     * <pre>
     * 'GATEWAY_PARALLEL': {
     *   d: 'm {mx},{my} {e.x0},0 0,{e.x1} {e.x1},0 0,{e.y0} -{e.x1},0 0,{e.y1} ' +
     '-{e.x0},0 0,-{e.y1} -{e.x1},0 0,-{e.y0} {e.x1},0 z',
     *   height: 17.5,
     *   width:  17.5,
     *   heightElements: [2.5, 7.5],
     *   widthElements: [2.5, 7.5]
     * }
     * </pre>
     * <p>It's important to specify a correct <b>height and width</b> for the path as the scaling
     * is based on the ratio between the specified height and width in this object and the
     * height and width that is set as scale target (Note x,y coordinates will be scaled with
     * individual ratios).</p>
     * <p>The '<b>heightElements</b>' and '<b>widthElements</b>' array must contain the values that will be scaled.
     * The scaling is based on the computed ratios.
     * Coordinates on the y axis should be in the <b>heightElement</b>'s array, they will be scaled using
     * the computed ratio coefficient.
     * In the parameterized path the scaled values can be accessed through the 'e' object in {} brackets.
     *   <ul>
     *    <li>The values for the y axis can be accessed in the path string using {e.y0}, {e.y1}, ....</li>
     *    <li>The values for the x axis can be accessed in the path string using {e.x0}, {e.x1}, ....</li>
     *   </ul>
     *   The numbers x0, x1 respectively y0, y1, ... map to the corresponding array index.
     * </p>
     */
    pathMap: {
        EVENT_MESSAGE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_SIGNAL: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_ESCALATION: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_CONDITIONAL: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_LINK: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_ERROR: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_CANCEL_45: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_COMPENSATION: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_TIMER_WH: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_TIMER_LINE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_MULTIPLE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        EVENT_PARALLEL_MULTIPLE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        GATEWAY_EXCLUSIVE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        GATEWAY_PARALLEL: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        GATEWAY_EVENT_BASED: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        GATEWAY_COMPLEX: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        DATA_OBJECT_PATH: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        DATA_OBJECT_COLLECTION_PATH: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        DATA_ARROW: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        DATA_STORE: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        TEXT_ANNOTATION: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        MARKER_SUB_PROCESS: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        MARKER_PARALLEL: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        MARKER_SEQUENTIAL: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        MARKER_COMPENSATION: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        MARKER_LOOP: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        MARKER_ADHOC: {
            d: string;
            height: number;
            width: number;
            heightElements: any[];
            widthElements: any[];
        };
        TASK_TYPE_SEND: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        TASK_TYPE_SCRIPT: {
            d: string;
            height: number;
            width: number;
            heightElements: number[];
            widthElements: number[];
        };
        TASK_TYPE_USER_1: {
            d: string;
        };
        TASK_TYPE_USER_2: {
            d: string;
        };
        TASK_TYPE_USER_3: {
            d: string;
        };
        TASK_TYPE_MANUAL: {
            d: string;
        };
        TASK_TYPE_INSTANTIATING_SEND: {
            d: string;
        };
        TASK_TYPE_SERVICE: {
            d: string;
        };
        TASK_TYPE_SERVICE_FILL: {
            d: string;
        };
        TASK_TYPE_BUSINESS_RULE_HEADER: {
            d: string;
        };
        TASK_TYPE_BUSINESS_RULE_MAIN: {
            d: string;
        };
        MESSAGE_FLOW_MARKER: {
            d: string;
        };
    };
    /**
     * Return raw path for the given ID.
     *
     * @param pathId
     *
     * @return raw path
     */
    getRawPath: (pathId: string) => string;
    /**
     * Scales the path to the given height and width.
     * <h1>Use case</h1>
     * <p>Use case is to scale the content of elements (event, gateways) based
     * on the element bounding box's size.
     * </p>
     * <h1>Why not transform</h1>
     * <p>Scaling a path with transform() will also scale the stroke and IE does not support
     * the option 'non-scaling-stroke' to prevent this.
     * Also there are use cases where only some parts of a path should be
     * scaled.</p>
     *
     * @param pathId The ID of the path.
     * @param param <p>
     *   Example param object scales the path to 60% size of the container (data.width, data.height).
     *   <pre>
     *   {
     *     xScaleFactor: 0.6,
     *     yScaleFactor:0.6,
     *     containerWidth: data.width,
     *     containerHeight: data.height,
     *     position: {
     *       mx: 0.46,
     *       my: 0.2,
     *     }
     *   }
     *   </pre>
     *   <ul>
     *    <li>targetpathwidth = xScaleFactor * containerWidth</li>
     *    <li>targetpathheight = yScaleFactor * containerHeight</li>
     *    <li>Position is used to set the starting coordinate of the path. M is computed:
     *    <ul>
     *      <li>position.x * containerWidth</li>
     *      <li>position.y * containerHeight</li>
     *    </ul>
     *    Center of the container <pre> position: {
     *       mx: 0.5,
     *       my: 0.5,
     *     }</pre>
     *     Upper left corner of the container
     *     <pre> position: {
     *       mx: 0.0,
     *       my: 0.0,
     *     }</pre>
     *    </li>
     *   </ul>
     * </p>
     *
     * @return scaled path
     */
    getScaledPath: (pathId: string, param: any) => string;
}
