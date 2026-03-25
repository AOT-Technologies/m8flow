/**
 * A component that renders the popup menus.
 *
 */
export default class PopupMenuComponent {
    /**
     * @param props
     */
    constructor(props: {
        onClose: () => void;
        onSelect: () => void;
        position: (element: HTMLElement) => Point;
        className: string;
        entries: PopupMenuEntry[];
        headerEntries: PopupMenuHeaderEntry[];
        scale: number;
        title?: string;
        search?: boolean;
        emptyPlaceholder?: PopupMenuEmptyPlaceholder;
        width?: number;
    });
}

type PopupMenuEntry = import('./PopupMenuProvider').PopupMenuEntry;
type PopupMenuHeaderEntry = import('./PopupMenuProvider').PopupMenuHeaderEntry;
export type PopupMenuEmptyPlaceholder = import('./PopupMenuProvider').PopupMenuEmptyPlaceholderProvider | import('./PopupMenuProvider').PopupMenuEmptyPlaceholder;
type Point = import('../../util/Types').Point;
