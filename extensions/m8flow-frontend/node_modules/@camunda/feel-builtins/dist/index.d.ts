/**
 * A collection of builtin of FEEL.
 */
export const camundaBuiltins: Builtin[];
export type Builtin = {
  /**
   * The name of the builtin function.
   */
  name: string;
  /**
   * A short description of the built-in function.
   */
  info: string;
  /**
   * type of the builtin, always 'function' for builtin functions.
   */
  type?: "function";
  /**
   * function parameters.
   */
  params?: Array<{
    name: string;
  }>;
};
