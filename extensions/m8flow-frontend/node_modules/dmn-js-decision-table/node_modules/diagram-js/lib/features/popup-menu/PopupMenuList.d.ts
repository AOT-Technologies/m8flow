/**
 * Component that renders a popup menu entry list.
 *
 */
export default class PopupMenuList {
    /**
     * @param props
     */
    constructor(props: {
        groupedEntries: PopupMenuGroup[];
        selectedEntry: PopupMenuEntry;
        setSelectedEntry: (entry: PopupMenuEntry | null) => void;
    });
}

type PopupMenuEntry = import("./PopupMenuProvider").PopupMenuEntry;
type PopupMenuGroup = import("./PopupMenuProvider").PopupMenuGroup;
