declare const names: string[];
declare const builtins: {
    number: {
        (...args: any[]): any;
        $args: any;
    };
    string: {
        (...args: any[]): any;
        $args: any;
    };
    date: {
        (...args: any[]): any;
        $args: any;
    };
    'date and time': {
        (...args: any[]): any;
        $args: any;
    };
    time: {
        (...args: any[]): any;
        $args: any;
    };
    duration: {
        (...args: any[]): any;
        $args: any;
    };
    'years and months duration': {
        (...args: any[]): any;
        $args: any;
    };
    '@': {
        (...args: any[]): any;
        $args: any;
    };
    now: {
        (...args: any[]): any;
        $args: any;
    };
    today: {
        (...args: any[]): any;
        $args: any;
    };
    not: {
        (...args: any[]): any;
        $args: any;
    };
    substring: {
        (...args: any[]): any;
        $args: any;
    };
    'string length': {
        (...args: any[]): any;
        $args: any;
    };
    'upper case': {
        (...args: any[]): any;
        $args: any;
    };
    'lower case': {
        (...args: any[]): any;
        $args: any;
    };
    'substring before': {
        (...args: any[]): any;
        $args: any;
    };
    'substring after': {
        (...args: any[]): any;
        $args: any;
    };
    replace: {
        (...args: any[]): any;
        $args: any;
    };
    contains: {
        (...args: any[]): any;
        $args: any;
    };
    matches: {
        (...args: any[]): any;
        $args: any;
    };
    'starts with': {
        (...args: any[]): any;
        $args: any;
    };
    'ends with': {
        (...args: any[]): any;
        $args: any;
    };
    split: {
        (...args: any[]): any;
        $args: any;
    };
    'string join': {
        (...args: any[]): any;
        $args: any;
    };
    'list contains': {
        (...args: any[]): any;
        $args: any;
    };
    'list replace': {
        (...args: any[]): any;
        $args: any;
    };
    count: {
        (...args: any[]): any;
        $args: any;
    };
    min: {
        (...args: any[]): any;
        $args: any;
    };
    max: {
        (...args: any[]): any;
        $args: any;
    };
    sum: {
        (...args: any[]): any;
        $args: any;
    };
    mean: {
        (...args: any[]): any;
        $args: any;
    };
    all: {
        (...args: any[]): any;
        $args: any;
    };
    any: {
        (...args: any[]): any;
        $args: any;
    };
    sublist: {
        (...args: any[]): any;
        $args: any;
    };
    append: {
        (...args: any[]): any;
        $args: any;
    };
    concatenate: {
        (...args: any[]): any;
        $args: any;
    };
    'insert before': {
        (...args: any[]): any;
        $args: any;
    };
    remove: {
        (...args: any[]): any;
        $args: any;
    };
    reverse: {
        (...args: any[]): any;
        $args: any;
    };
    'index of': {
        (...args: any[]): any;
        $args: any;
    };
    union: {
        (...args: any[]): any;
        $args: any;
    };
    'distinct values': {
        (...args: any[]): any;
        $args: any;
    };
    flatten: {
        (...args: any[]): any;
        $args: any;
    };
    product: {
        (...args: any[]): any;
        $args: any;
    };
    median: {
        (...args: any[]): any;
        $args: any;
    };
    stddev: {
        (...args: any[]): any;
        $args: any;
    };
    mode: {
        (...args: any[]): any;
        $args: any;
    };
    decimal: {
        (...args: any[]): any;
        $args: any;
    };
    floor: {
        (...args: any[]): any;
        $args: any;
    };
    ceiling: {
        (...args: any[]): any;
        $args: any;
    };
    abs: {
        (...args: any[]): any;
        $args: any;
    };
    'round up': {
        (...args: any[]): any;
        $args: any;
    };
    'round down': {
        (...args: any[]): any;
        $args: any;
    };
    'round half up': {
        (...args: any[]): any;
        $args: any;
    };
    'round half down': {
        (...args: any[]): any;
        $args: any;
    };
    modulo: {
        (...args: any[]): any;
        $args: any;
    };
    sqrt: {
        (...args: any[]): any;
        $args: any;
    };
    log: {
        (...args: any[]): any;
        $args: any;
    };
    exp: {
        (...args: any[]): any;
        $args: any;
    };
    odd: {
        (...args: any[]): any;
        $args: any;
    };
    even: {
        (...args: any[]): any;
        $args: any;
    };
    is: {
        (...args: any[]): any;
        $args: any;
    };
    before: {
        (...args: any[]): any;
        $args: any;
    };
    after: {
        (...args: any[]): any;
        $args: any;
    };
    meets: {
        (...args: any[]): any;
        $args: any;
    };
    'met by': {
        (...args: any[]): any;
        $args: any;
    };
    overlaps: {
        (...args: any[]): any;
        $args: any;
    };
    'overlaps before': {
        (...args: any[]): any;
        $args: any;
    };
    'overlaps after': {
        (...args: any[]): any;
        $args: any;
    };
    finishes: {
        (...args: any[]): any;
        $args: any;
    };
    'finished by': {
        (...args: any[]): any;
        $args: any;
    };
    includes: {
        (...args: any[]): any;
        $args: any;
    };
    during: {
        (...args: any[]): any;
        $args: any;
    };
    starts: {
        (...args: any[]): any;
        $args: any;
    };
    'started by': {
        (...args: any[]): any;
        $args: any;
    };
    coincides: {
        (...args: any[]): any;
        $args: any;
    };
    'day of year': {
        (...args: any[]): any;
        $args: any;
    };
    'day of week': {
        (...args: any[]): any;
        $args: any;
    };
    'month of year': {
        (...args: any[]): any;
        $args: any;
    };
    'week of year': {
        (...args: any[]): any;
        $args: any;
    };
    sort: {
        (...args: any[]): any;
        $args: any;
    };
    'get value': {
        (...args: any[]): any;
        $args: any;
    };
    'get entries': {
        (...args: any[]): any;
        $args: any;
    };
    context: {
        (...args: any[]): any;
        $args: any;
    };
    'context merge': {
        (...args: any[]): any;
        $args: any;
    };
    'context put': {
        (...args: any[]): any;
        $args: any;
    };
};
export { names, builtins };
