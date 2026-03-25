import { SyntaxNodeRef } from '@lezer/common';
type SyntaxErrorDetails = {
    input: string;
    position: {
        from: number;
        to: number;
    };
};
export declare class SyntaxError extends Error {
    input: string;
    position: {
        from: number;
        to: number;
    };
    constructor(message: string, details: SyntaxErrorDetails);
}
export type InterpreterContext = Record<string, any>;
export declare function unaryTest(expression: string, context?: InterpreterContext, dialect?: string): boolean;
export declare function evaluate(expression: string, context?: InterpreterContext, dialect?: string): any;
type LintError = {
    from: number;
    to: number;
    message: string;
};
export declare function lintError(nodeRef: SyntaxNodeRef): LintError;
export {};
