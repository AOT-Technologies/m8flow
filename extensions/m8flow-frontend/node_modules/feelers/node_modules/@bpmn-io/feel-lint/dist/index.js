'use strict';

var lezerFeel = require('lezer-feel');
var language = require('@codemirror/language');

/**
 * @typedef {import('@lezer/common').Tree} Tree
 * @typedef {import('@codemirror/lint').Diagnostic} LintMessage
 */

/**
 * Create an array of syntax errors in the given tree.
 *
 * @param {Tree} syntaxTree
 * @returns {LintMessage[]} array of syntax errors
 */
function lintSyntax(syntaxTree) {

  const lintMessages = [];

  syntaxTree.iterate({
    enter: ref => {
      const node = ref.node;

      if (!node.type.isError) {
        return;
      }

      const parent = node.parent;
      const next = getNextNode(node);

      const message = {
        from: node.from,
        to: node.to,
        severity: 'error',
        type: 'Syntax Error'
      };

      if (node.from !== node.to) {
        message.message = `Unrecognized token in <${parent.name}>`;
      } else if (next) {
        message.message = `Unrecognized token <${next.name}> in <${parent.name}>`;
        message.to = next.to;
      } else {
        const before = parent.enterUnfinishedNodesBefore(node.to);
        message.message = `Incomplete <${ (before || parent).name }>`;
      }

      lintMessages.push(message);
    }
  });

  return lintMessages;
}

function getNextNode(node) {
  if (!node) {
    return null;
  }

  return node.nextSibling || getNextNode(node.parent);
}

/**
 * @typedef {object} Context
 * @property {function} report
 * @property {(from: number, to: number) => string} readContent
 * @property {(from: number, to: number, content: string) => void} updateContent
 */

const RULE_NAME = 'first-item';

var firstItem = {
  create(/** @type {Context} */ context) {
    return {
      enter(node) {
        if (node.name !== 'FilterExpression') {
          return;
        }

        const content = context.readContent(node.from, node.to);

        if (zeroIndexPattern().test(content)) {
          const {
            from,
            to
          } = node;

          context.report({
            from,
            to,
            message: 'First item is accessed via [1]',
            severity: 'warning',
            type: RULE_NAME,
            actions: [
              {
                name: 'fix',
                apply(_, start = from, end = to) {
                  context.updateContent(start, end, content.replace(zeroIndexPattern(), '[1]'));
                }
              }
            ]
          });
        }
      }
    };
  }
};

function zeroIndexPattern() {
  return /\[\s*0\s*\]$/;
}

/**
 * @typedef {import('@lezer/common').Tree} Tree
 * @typedef {import('@codemirror/lint').Diagnostic} LintMessage
 * @typedef {import('./index').LintAllContext} LintAllContext
 */

const RULES = [
  firstItem
];

/**
 * Create an array of messages reported from rules in the given tree.
 *
 * @param {LintAllContext} context
 * @returns {LintMessage[]} array of syntax errors
 */
function lintRules(context) {
  const {
    readContent,
    syntaxTree,
    updateContent
  } = context;

  const lintMessages = [];

  const ruleContext = {
    readContent,
    report: message => {
      lintMessages.push(message);
    },
    updateContent
  };

  const rules = RULES.map(rule => rule.create(ruleContext));

  syntaxTree.iterate({
    enter: ref => {
      for (const rule of rules) {
        rule.enter && rule.enter(ref);
      }
    },
    leave: ref => {
      for (const rule of rules) {
        rule.leave && rule.leave(ref);
      }
    }
  });

  return lintMessages;
}

/**
 * @typedef {import('@lezer/common').Tree} Tree
 * @typedef {import('@codemirror/lint').Diagnostic} LintMessage
 */

/**
 * @typedef {object} LintAllContext
 * @property {Tree} syntaxTree
 * @property {(from: number, to: number) => string} readContent
 * @property {(from: number, to: number, content: string) => void} updateContent
 */

/**
 * Generates lint messages for the given context.
 *
 * @param {LintAllContext} context
 * @returns {LintMessage[]} array of all lint messages
 */
function lintAll(context) {

  const lintMessages = [
    ...lintSyntax(context.syntaxTree),
    ...lintRules(context)
  ];

  return lintMessages;
}

/**
 * Create an array of syntax errors for the given expression.
 *
 * @param {String} expression
 * @param { {
 *   dialect?: 'expression' | 'unaryTests',
 *   context?: Record<string, any>,
 *   parserDialect?: string
 * } } [lintOptions]
 *
 * @returns {LintMessage[]} array of syntax errors
 */
function lintExpression(expression, {
  dialect = 'expression',
  parserDialect,
  context = {}
} = {}) {

  const syntaxTree = lezerFeel.parser.configure({
    top: dialect === 'unaryTests' ? 'UnaryTests' : 'Expression',
    dialect: parserDialect,
    contextTracker: lezerFeel.trackVariables(context)
  }).parse(expression);

  const lintMessages = lintAll({
    syntaxTree,
    readContent: (from, to) => expression.slice(from, to),
    updateContent: (from, to, content) => {

      // not implemented
    }
  });

  return lintMessages;
}

/**
 * CodeMirror extension that provides linting for FEEL expressions.
 *
 * @returns {import('@codemirror/lint').LintSource} CodeMirror linting source
 */
const cmFeelLinter = () => editorView => {

  // don't lint if the Editor is empty
  if (editorView.state.doc.length === 0) {
    return [];
  }

  const tree = language.syntaxTree(editorView.state);

  const messages = lintAll({
    syntaxTree: tree,
    readContent: (from, to) => editorView.state.sliceDoc(from, to),
    updateContent: (from, to, content) => editorView.dispatch({
      changes: { from, to, insert: content }
    })
  });

  return messages.map(message => ({
    ...message,
    source: message.type
  }));
};

exports.cmFeelLinter = cmFeelLinter;
exports.lintExpression = lintExpression;
