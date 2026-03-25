import { DateTime, Duration } from 'luxon';
export declare function isContext(e: any): boolean;
export declare function isDateTime(obj: any): obj is DateTime;
export declare function isDuration(obj: any): obj is Duration;
export declare function isArray(e: any): e is any[];
export declare function isBoolean(e: any): e is boolean;
export declare function getType(e: any): "string" | "number" | "literal" | "boolean" | "nil" | "context" | "list" | "duration" | "time" | "date" | "date time" | "range" | "function";
export declare function isType(el: string, type: string): boolean;
export declare function typeCast(obj: any, type: string): DateTime<boolean>;
export type RangeProps = {
    'start included': boolean;
    'end included': boolean;
    start: string | number | null;
    end: string | number | null;
    map: <T>(fn: (val: any) => T) => T[];
    includes: (val: any) => boolean;
};
export declare class Range {
    'start included': boolean;
    'end included': boolean;
    start: string | number | null;
    end: string | number | null;
    map: <T>(fn: (val: any) => T) => T[];
    includes: (val: any) => boolean;
    constructor(props: RangeProps);
}
export declare function isNumber(obj: any): obj is number;
export declare function isString(obj: any): obj is string;
export declare function equals(a: any, b: any, strict?: boolean): any;
export declare class FunctionWrapper {
    fn: (...args: any[]) => any;
    parameterNames: string[];
    constructor(fn: (...args: any[]) => any, parameterNames: string[]);
    invoke(contextOrArgs: any): any;
}
