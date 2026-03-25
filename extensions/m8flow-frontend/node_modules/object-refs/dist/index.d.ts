export type AttributeDescriptor = {
  name: string;
  collection?: boolean | undefined;
  enumerable?: boolean | undefined;
}

export class Refs {

  /**
   * Creates a new references object defining two inversly related
   * attribute descriptors a and b.
   *
   * @param a property descriptor
   * @param b property descriptor
   */
  constructor(a: AttributeDescriptor, b: AttributeDescriptor);

  /**
   * Binds one side of a bi-directional reference to a target object.
   *
   * @param target
   * @param property
   */
  bind(target: any, property: string | AttributeDescriptor): void;

  ensureBound(target: any, property: string | AttributeDescriptor): void;

  ensureRefsCollection(target: any, property: AttributeDescriptor): any;

  set(target: any, property: string | AttributeDescriptor, value: any): void;

  unset(target: any, property: string | AttributeDescriptor, value: any): void;
}

export namespace Collection {

  /**
   * Extends a collection with Refs aware methods
   */
  function extend(collection: any[], refs: Refs, property: string | AttributeDescriptor, target: any): any;

  /**
   * Checks if a given collection is extended
   */
  function isExtended(collection: any[]): boolean;

}