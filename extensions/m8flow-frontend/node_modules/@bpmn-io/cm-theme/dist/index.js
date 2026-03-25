'use strict';

var view = require('@codemirror/view');
var language = require('@codemirror/language');
var highlight = require('@lezer/highlight');

const highlightStyle$2 = language.syntaxHighlighting(language.HighlightStyle.define([
  { tag: highlight.tags.strong, fontWeight: 'bold' },
  { tag: highlight.tags.emphasis, fontStyle: 'italic' },
]));

const theme$2 = view.EditorView.theme({
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

const theme$1 = view.EditorView.theme(
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

const highlightStyle$1 = language.syntaxHighlighting(language.HighlightStyle.define([
  {
    tag: [ highlight.tags.macroName, highlight.tags.variableName ],
    color: colors.waterBlue
  },
  {
    tag: [ highlight.tags.special(highlight.tags.bracket) ],
    color: colors.waterBlue,
    fontWeight: 'bold'
  },
  {
    tag: [ highlight.tags.color, highlight.tags.name, highlight.tags.definition(highlight.tags.name), highlight.tags.constant(highlight.tags.name), highlight.tags.standard(highlight.tags.name), highlight.tags.propertyName, ],
    color: colors.deepBlue
  },
  {
    tag: [ highlight.tags.definition(highlight.tags.variableName), highlight.tags.function(highlight.tags.variableName), highlight.tags.function(highlight.tags.propertyName) ],
    color: colors.brightBlue,
  },
  { tag: [ highlight.tags.labelName ], color: colors.orangeBrown },
  {
    tag: [ highlight.tags.annotation ],
    color: colorByRole.invalid
  },
  {
    tag: [ highlight.tags.number, highlight.tags.changed, highlight.tags.annotation, highlight.tags.modifier, highlight.tags.self, highlight.tags.namespace, highlight.tags.atom, highlight.tags.bool, highlight.tags.special(highlight.tags.variableName) ],
    color: colors.red
  },
  {
    tag: [ highlight.tags.typeName, highlight.tags.className, highlight.tags.attributeName ],
    color: colors.lila
  },
  {
    tag: [ highlight.tags.operator, highlight.tags.operatorKeyword, highlight.tags.tagName, highlight.tags.keyword ],
    color: colors.purple
  },
  {
    tag: [ highlight.tags.angleBracket, highlight.tags.squareBracket, highlight.tags.brace, highlight.tags.separator, highlight.tags.punctuation ],
    color: colors.midGrey
  },
  {
    tag: [ highlight.tags.regexp ],
    color: colors.deepBlue
  },
  {
    tag: [ highlight.tags.quote ],
    color: colors.darkGrey
  },
  { tag: [ highlight.tags.string, highlight.tags.character, highlight.tags.deleted ], color: colors.orangeBrown },
  {
    tag: highlight.tags.link,
    color: colors.mossGreen,
    textDecoration: 'underline',
    textUnderlinePosition: 'under'
  },
  {
    tag: [ highlight.tags.url, highlight.tags.escape, highlight.tags.special(highlight.tags.string) ],
    color: colors.red
  },
  { tag: [ highlight.tags.meta ], color: colors.iceBlue },
  { tag: [ highlight.tags.comment ], color: colors.midGrey, fontStyle: 'italic' },
  { tag: highlight.tags.strong, fontWeight: 'bold', color: colors.deepBlue },
  { tag: highlight.tags.emphasis, fontStyle: 'italic', color: colors.deepBlue },
  { tag: highlight.tags.strikethrough, textDecoration: 'line-through' },
  { tag: highlight.tags.heading, fontWeight: 'bold', color: colors.midGray },
  { tag: highlight.tags.special(highlight.tags.heading1), fontWeight: 'bold', color: colors.darkGrey },
  {
    tag: [ highlight.tags.heading1, highlight.tags.heading2, highlight.tags.heading3, highlight.tags.heading4 ],
    fontWeight: 'bold',
    color: colors.midGrey
  },
  { tag: [ highlight.tags.heading5, highlight.tags.heading6, highlight.tags.processingInstruction, highlight.tags.inserted ], color: colors.grey },
  {
    tag: [ highlight.tags.contentSeparator ],
    color: colors.yellow
  },
  { tag: highlight.tags.invalid, color: colors.midGrey, borderBottom: `1px dotted ${colorByRole.invalid}` }
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

const theme = view.EditorView.theme(
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

const highlightStyle = language.syntaxHighlighting(language.HighlightStyle.define([

  // Markdown headings
  { tag: highlight.tags.heading1, color: pastelYellow },
  { tag: highlight.tags.heading2, color: pastelYellow },
  { tag: highlight.tags.heading3, color: pastelYellow },
  { tag: highlight.tags.heading4, color: pastelYellow },
  { tag: highlight.tags.heading5, color: pastelYellow },
  { tag: highlight.tags.heading6, color: pastelYellow },

  // Feelers
  { tag: highlight.tags.special(highlight.tags.bracket), color: pastelOrange, fontWeight: 'bold' },

  // Everything else
  { tag: highlight.tags.keyword, color: '#c792ea' },
  { tag: highlight.tags.operator, color: '#89ddff' },
  { tag: highlight.tags.special(highlight.tags.variableName), color: '#eeffff' },
  { tag: highlight.tags.typeName, color: '#f07178' },
  { tag: highlight.tags.atom, color: '#f78c6c' },
  { tag: highlight.tags.number, color: '#ff5370' },
  { tag: highlight.tags.bool, color: '#ff5370' },
  { tag: highlight.tags.definition(highlight.tags.variableName), color: '#82aaff' },
  { tag: highlight.tags.string, color: '#c3e88d' },
  { tag: highlight.tags.comment, color: stone },
  { tag: highlight.tags.tagName, color: '#ff5370' },
  { tag: highlight.tags.bracket, color: '#a2a1a4' },
  { tag: highlight.tags.meta, color: '#ffcb6b' },
  { tag: highlight.tags.special(highlight.tags.string), color: peach },
  { tag: highlight.tags.propertyName, color: pastelOrange },
  { tag: highlight.tags.variableName, color: pastelOrange },
  { tag: highlight.tags.attributeName, color: peach },
  { tag: highlight.tags.className, color: peach },
  { tag: highlight.tags.invalid, color: invalid }
]));

var bpmnioDark = [
  theme,
  highlightStyle
];

const lightTheme = [ ...commonTheme, ...bpmnioLight ];
const darkTheme = [ ...commonTheme, ...bpmnioDark ];

exports.darkTheme = darkTheme;
exports.lightTheme = lightTheme;
