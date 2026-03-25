import { EditorView } from '@codemirror/view';
import { syntaxHighlighting, HighlightStyle } from '@codemirror/language';
import { tags } from '@lezer/highlight';

const highlightStyle$2 = syntaxHighlighting(HighlightStyle.define([
  { tag: tags.strong, fontWeight: 'bold' },
  { tag: tags.emphasis, fontStyle: 'italic' },
]));

const theme$2 = EditorView.theme({
  '& .cm-lintRange': {
    position: 'relative',
  },
  '& .cm-lintRange::after': {
    content: '""',
    width: '100%',
    position: 'absolute',
    left: '0px',
    bottom: '-2px',
    height: '3px',
    backgroundRepeat: 'repeat-x',
  },
  '& .cm-lintRange.cm-lintRange-warning, & .cm-lintRange.cm-lintRange-error': {
    backgroundImage: 'none',
  },
  '& .cm-lintPoint::after': {
    bottom: '-2px'
  }
});

var commonTheme = [
  theme$2,
  highlightStyle$2
];

const _urlify = (color) => `%23${color.slice(1)}`;

const colors = {
  black: '#1f2b36',
  darkGrey: '#2f3d58',
  grey: '#404a5c',
  midGrey: '#576071',
  lightGrey: '#c5d1e5',
  offWhite: '#d9e0f5',
  snowWhite: '#eaf1ff',
  white: '#ffffff',
  mossGreen: '#7ab6aa',
  iceBlue: '#6cbfd8',
  waterBlue: '#065aaa',
  brightBlue: '#0a56b9',
  deepBlue: '#355472',
  red: '#9f1c15',
  orangeBrown: '#b4502f',
  yellow: '#debd71',
  lila: '#9a4890',
  purple: '#5b2c83'
};

const colorByRole = {
  lightBackground: colors.white,
  darkBackground: colors.snowWhite,
  selection: colors.snowWhite,
  tooltipBackground: colors.offWhite,
  error: colors.red,
  warning: colors.yellow,
  invalid: '#b40000'
};

const theme$1 = EditorView.theme(
  {
    '&': { color: colors.black, backgroundColor: colorByRole.lightBackground },
    '.cm-content': { caretColor: colors.darkGrey },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: colors.darkGrey },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
      { backgroundColor: colorByRole.selection },

    '.cm-panels': { backgroundColor: colorByRole.darkBackground, color: colors.grey },
    '.cm-panels.cm-panels-top': { borderBottom: `2px solid ${ colors.black }` },
    '.cm-panels.cm-panels-bottom': { borderTop: `2px solid ${ colors.black }` },

    '.cm-searchMatch': {
      backgroundColor: '#72a1ff59',
      outline: `1px solid ${colors.midGrey}`
    },
    '.cm-searchMatch.cm-searchMatch-selected': { backgroundColor: colors.offWhite },
    '.cm-activeLine': { backgroundColor: colorByRole.selection },
    '.cm-selectionMatch': { backgroundColor: colors.offWhite },

    '&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket': {
      outline: `1px solid ${colors.grey}`
    },

    '&.cm-focused .cm-matchingBracket': {
      backgroundColor: colors.snowWhite
    },

    '.cm-gutters': {
      backgroundColor: '#f3f7fe',
      color: '#52668d',
      border: 'none',
      padding: '0 5px'
    },

    '.cm-activeLineGutter': {
      backgroundColor: colorByRole.selection
    },

    '.cm-foldPlaceholder': {
      backgroundColor: 'transparent',
      border: 'none',
      color: '#ddd'
    },

    '.cm-tooltip': {
      border: 'none',
      backgroundColor: colorByRole.tooltipBackground
    },
    '.cm-tooltip .cm-tooltip-arrow:before': {
      borderTopColor: 'transparent',
      borderBottomColor: 'transparent'
    },
    '.cm-tooltip .cm-tooltip-arrow:after': {
      borderTopColor: colorByRole.tooltipBackground,
      borderBottomColor: colorByRole.tooltipBackground
    },
    '.cm-tooltip-autocomplete': {
      '& > ul > li[aria-selected]': {
        backgroundColor: colorByRole.darkBackground,
        color: colors.midGrey
      }
    },
    '& .cm-lintRange.cm-lintRange-warning::after': {
      backgroundImage: `url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='6' height='3'><path d='m0 2.5 l2 -1.5 l1 0 l2 1.5 l1 0' stroke='${_urlify(colorByRole.warning)}' fill='none' stroke-width='1.2'/></svg>")`,
    },
    '& .cm-lintRange.cm-lintRange-error::after': {
      backgroundImage: `url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='6' height='3'><path d='m0 2.5 l2 -1.5 l1 0 l2 1.5 l1 0' stroke='${_urlify(colorByRole.error)}' fill='none' stroke-width='1.2'/></svg>")`,
    },
    '& .cm-diagnostic-warning': {
      border: `1px solid ${colorByRole.warning}`,
      borderLeft: `5px solid ${colorByRole.warning}`,
      background: colorByRole.lightBackground,
    },
    '& .cm-diagnostic-error': {
      border: `1px solid ${colorByRole.error}`,
      borderLeft: `5px solid ${colorByRole.error}`,
      background: colorByRole.lightBackground
    },
    '& .cm-diagnostic': {
      padding: '3px 8px'
    }
  },
  { dark: false }
);

const highlightStyle$1 = syntaxHighlighting(HighlightStyle.define([
  {
    tag: [ tags.macroName, tags.variableName ],
    color: colors.waterBlue
  },
  {
    tag: [ tags.special(tags.bracket) ],
    color: colors.waterBlue,
    fontWeight: 'bold'
  },
  {
    tag: [ tags.color, tags.name, tags.definition(tags.name), tags.constant(tags.name), tags.standard(tags.name), tags.propertyName, ],
    color: colors.deepBlue
  },
  {
    tag: [ tags.definition(tags.variableName), tags.function(tags.variableName), tags.function(tags.propertyName) ],
    color: colors.brightBlue,
  },
  { tag: [ tags.labelName ], color: colors.orangeBrown },
  {
    tag: [ tags.annotation ],
    color: colorByRole.invalid
  },
  {
    tag: [ tags.number, tags.changed, tags.annotation, tags.modifier, tags.self, tags.namespace, tags.atom, tags.bool, tags.special(tags.variableName) ],
    color: colors.red
  },
  {
    tag: [ tags.typeName, tags.className, tags.attributeName ],
    color: colors.lila
  },
  {
    tag: [ tags.operator, tags.operatorKeyword, tags.tagName, tags.keyword ],
    color: colors.purple
  },
  {
    tag: [ tags.angleBracket, tags.squareBracket, tags.brace, tags.separator, tags.punctuation ],
    color: colors.midGrey
  },
  {
    tag: [ tags.regexp ],
    color: colors.deepBlue
  },
  {
    tag: [ tags.quote ],
    color: colors.darkGrey
  },
  { tag: [ tags.string, tags.character, tags.deleted ], color: colors.orangeBrown },
  {
    tag: tags.link,
    color: colors.mossGreen,
    textDecoration: 'underline',
    textUnderlinePosition: 'under'
  },
  {
    tag: [ tags.url, tags.escape, tags.special(tags.string) ],
    color: colors.red
  },
  { tag: [ tags.meta ], color: colors.iceBlue },
  { tag: [ tags.comment ], color: colors.midGrey, fontStyle: 'italic' },
  { tag: tags.strong, fontWeight: 'bold', color: colors.deepBlue },
  { tag: tags.emphasis, fontStyle: 'italic', color: colors.deepBlue },
  { tag: tags.strikethrough, textDecoration: 'line-through' },
  { tag: tags.heading, fontWeight: 'bold', color: colors.midGray },
  { tag: tags.special(tags.heading1), fontWeight: 'bold', color: colors.darkGrey },
  {
    tag: [ tags.heading1, tags.heading2, tags.heading3, tags.heading4 ],
    fontWeight: 'bold',
    color: colors.midGrey
  },
  { tag: [ tags.heading5, tags.heading6, tags.processingInstruction, tags.inserted ], color: colors.grey },
  {
    tag: [ tags.contentSeparator ],
    color: colors.yellow
  },
  { tag: tags.invalid, color: colors.midGrey, borderBottom: `1px dotted ${colorByRole.invalid}` }
]));

var bpmnioLight = [
  theme$1,
  highlightStyle$1
];

const ivory = '#abb2bf',
      peach = '#f07178',
      stone = '#7d8799',
      invalid = '#ffffff',
      pastelYellow = '#fffce1',
      pastelOrange = '#ec9e6f',
      raisinBlack = '#21252b',
      highlightBackground = 'rgba(0, 0, 0, 0.5)',
      background = '#292d3e',
      tooltipBackground = '#353a42',
      selection = 'rgba(128, 203, 196, 0.2)',
      cursor = '#ffcc00';

const urlHash = '%23';
const warningColorHex = 'fff890';
const errorColor = 'red';
const warningBackgroundColor = '#281e16';
const errorBackgroundColor = '#281616';

const theme = EditorView.theme(
  {
    '&': {
      color: '#ffffff',
      backgroundColor: background
    },
    '.cm-content': {
      caretColor: cursor
    },
    '&.cm-focused .cm-cursor': {
      borderLeftColor: cursor
    },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection':
      { backgroundColor: selection },
    '.cm-panels': { backgroundColor: raisinBlack, color: '#ffffff' },
    '.cm-panels.cm-panels-top': { borderBottom: '2px solid black' },
    '.cm-panels.cm-panels-bottom': { borderTop: '2px solid black' },
    '.cm-searchMatch': {
      backgroundColor: '#72a1ff59',
      outline: '1px solid #457dff'
    },
    '.cm-searchMatch.cm-searchMatch-selected': {
      backgroundColor: '#6199ff2f'
    },
    '.cm-activeLine': { backgroundColor: highlightBackground },
    '.cm-selectionMatch': { backgroundColor: '#aafe661a' },
    '&.cm-focused .cm-matchingBracket, &.cm-focused .cm-nonmatchingBracket': {
      backgroundColor: '#bad0f847',
      outline: '1px solid #515a6b'
    },
    '.cm-gutters': {
      background: '#292d3e',
      color: '#676e95',
      border: 'none',
      padding: '0 5px'
    },
    '.cm-activeLineGutter': {
      backgroundColor: highlightBackground
    },
    '.cm-foldPlaceholder': {
      backgroundColor: 'transparent',
      border: 'none',
      color: '#ddd'
    },
    '.cm-tooltip': {
      border: 'none',
      backgroundColor: tooltipBackground
    },
    '.cm-tooltip .cm-tooltip-arrow:before': {
      borderTopColor: 'transparent',
      borderBottomColor: 'transparent'
    },
    '.cm-tooltip .cm-tooltip-arrow:after': {
      borderTopColor: tooltipBackground,
      borderBottomColor: tooltipBackground
    },
    '.cm-tooltip-autocomplete': {
      '& > ul > li[aria-selected]': {
        backgroundColor: highlightBackground,
        color: ivory
      }
    },
    '& .cm-lintRange.cm-lintRange-warning::after': {
      backgroundImage: `url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='6' height='3'><path d='m0 2.5 l2 -1.5 l1 0 l2 1.5 l1 0' stroke='${urlHash + warningColorHex}' fill='none' stroke-width='1.2'/></svg>")`,
    },
    '& .cm-lintRange.cm-lintRange-error::after': {
      backgroundImage: `url("data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='6' height='3'><path d='m0 2.5 l2 -1.5 l1 0 l2 1.5 l1 0' stroke='${errorColor}' fill='none' stroke-width='1.2'/></svg>")`,
    },
    '& .cm-diagnostic-warning': {
      borderLeft: `5px solid #${warningColorHex}`,
      background: warningBackgroundColor
    },
    '& .cm-diagnostic-error': {
      borderLeft: `5px solid ${errorColor}`,
      background: errorBackgroundColor
    },
    '& .cm-diagnostic': {
      borderRadius: '2px',
      padding: '3px 8px'
    }
  },
  { dark: true }
);

const highlightStyle = syntaxHighlighting(HighlightStyle.define([

  // Markdown headings
  { tag: tags.heading1, color: pastelYellow },
  { tag: tags.heading2, color: pastelYellow },
  { tag: tags.heading3, color: pastelYellow },
  { tag: tags.heading4, color: pastelYellow },
  { tag: tags.heading5, color: pastelYellow },
  { tag: tags.heading6, color: pastelYellow },

  // Feelers
  { tag: tags.special(tags.bracket), color: pastelOrange, fontWeight: 'bold' },

  // Everything else
  { tag: tags.keyword, color: '#c792ea' },
  { tag: tags.operator, color: '#89ddff' },
  { tag: tags.special(tags.variableName), color: '#eeffff' },
  { tag: tags.typeName, color: '#f07178' },
  { tag: tags.atom, color: '#f78c6c' },
  { tag: tags.number, color: '#ff5370' },
  { tag: tags.bool, color: '#ff5370' },
  { tag: tags.definition(tags.variableName), color: '#82aaff' },
  { tag: tags.string, color: '#c3e88d' },
  { tag: tags.comment, color: stone },
  { tag: tags.tagName, color: '#ff5370' },
  { tag: tags.bracket, color: '#a2a1a4' },
  { tag: tags.meta, color: '#ffcb6b' },
  { tag: tags.special(tags.string), color: peach },
  { tag: tags.propertyName, color: pastelOrange },
  { tag: tags.variableName, color: pastelOrange },
  { tag: tags.attributeName, color: peach },
  { tag: tags.className, color: peach },
  { tag: tags.invalid, color: invalid }
]));

var bpmnioDark = [
  theme,
  highlightStyle
];

const lightTheme = [ ...commonTheme, ...bpmnioLight ];
const darkTheme = [ ...commonTheme, ...bpmnioDark ];

export { darkTheme, lightTheme };
