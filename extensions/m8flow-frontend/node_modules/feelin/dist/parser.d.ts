import { Tree } from '@lezer/common';
export type ParseContext = Record<string, any>;
export declare function parseExpression(expression: string, context?: ParseContext, dialect?: string): Tree;
export declare function parseUnaryTests(expression: string, context?: ParseContext, dialect?: string): Tree;
