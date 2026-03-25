declare const _default: {
  canvas: (string | typeof Canvas)[];
  elementRegistry: (string | typeof ElementRegistry)[];
  elementFactory: (string | typeof ElementFactory)[];
  eventBus: (string | typeof EventBus)[];
  graphicsFactory: (string | typeof GraphicsFactory)[];
};
export default _default;
import Canvas from './Canvas';
import ElementRegistry from './ElementRegistry';
import ElementFactory from './ElementFactory';
import EventBus from './EventBus';
import GraphicsFactory from './GraphicsFactory';
