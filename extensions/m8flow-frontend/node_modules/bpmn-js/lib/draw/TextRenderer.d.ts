/**
 * Renders text and computes text bounding boxes.
 *
 */
export default class TextRenderer {
    static $inject: string[];
    /**
     * @param config
     */
    constructor(config?: TextRendererConfig);
    /**
     * Get the new bounds of an externally rendered,
     * layouted label.
     *
     * @param bounds
     * @param text
     *
     * @return
     */
    getExternalLabelBounds: (bounds: Rect, text: string) => Rect;
    /**
     * Get the new bounds of text annotation.
     *
     * @param bounds
     * @param text
     *
     * @return
     */
    getTextAnnotationBounds: (bounds: Rect, text: string) => Rect;
    /**
     * Create a layouted text element.
     *
     * @param text
     * @param options
     *
     * @return rendered text
     */
    createText: (text: string, options?: TextLayoutConfig) => SVGElement;
    /**
     * Get default text style.
     */
    getDefaultStyle: () => {
        fontFamily: string;
        fontSize: number;
        fontWeight: string;
        lineHeight: number;
    } & Partial<TextRendererStyle>;
    /**
     * Get the external text style.
     */
    getExternalStyle: () => {
        fontFamily: string;
        fontSize: number;
        fontWeight: string;
        lineHeight: number;
    } & Partial<TextRendererStyle> & {
        fontSize: number;
    };
}

export type TextRendererStyle = {
    fontFamily: string;
    fontSize: number;
    fontWeight: string;
    lineHeight: number;
};

export type TextRendererConfig = {
    defaultStyle?: Partial<TextRendererStyle>;
    externalStyle?: Partial<TextRendererStyle>;
};

type TextLayoutConfig = import('diagram-js/lib/util/Text').TextLayoutConfig;
type Rect = import('diagram-js/lib/util/Types').Rect;
