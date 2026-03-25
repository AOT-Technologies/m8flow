import { DateTime, Duration, Zone } from 'luxon';
import { isDateTime, isDuration } from './types';
export { isDateTime, isDuration };
export declare function ms(temporal: any): number;
export declare function duration(opts: string | number): Duration;
export declare function date(str?: string, time?: string, zone?: Zone): DateTime;
