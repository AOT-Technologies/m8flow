import { SyntaxNode } from '@lezer/common';
import { CompletionSource, Completion } from '@codemirror/autocomplete';
export declare function contextualKeyword(options: {
    before?: string;
    after?: string;
    context: string;
    keyword: string;
}): CompletionSource;
export declare const keywordCompletions: CompletionSource[];
export declare const dontComplete: string[];
export declare const doComplete: string[];
export declare function ifExpression(completionSource: CompletionSource): CompletionSource;
export declare function snippetCompletion(snippets: readonly Completion[]): CompletionSource;
export declare function matchLeft(node: SyntaxNode, position: number, nodes: (string | undefined)[]): SyntaxNode | null;
export declare function matchRight(node: SyntaxNode, position: number, nodes: (string | undefined)[]): SyntaxNode | null;
export declare function matchChildren(node: SyntaxNode, position: number, nodes: (string | undefined)[], direction: 1 | -1): SyntaxNode | null;
export declare function ifInside(options: {
    nodes: string | string[];
    keyword: string;
    before?: string;
    after?: string;
}, source: CompletionSource): CompletionSource;
