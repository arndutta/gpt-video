import { JSDOM } from 'jsdom';

// This is a DOM event environment, not a real browser or layout engine.
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://127.0.0.1:5173/', pretendToBeVisual: true,
});
for (const key of ['window', 'document', 'navigator', 'HTMLElement', 'HTMLInputElement',
  'HTMLSelectElement', 'HTMLTextAreaElement', 'Node', 'Element', 'MutationObserver',
  'Event', 'MouseEvent', 'KeyboardEvent', 'File', 'FileList', 'FormData', 'localStorage']) {
  Object.defineProperty(globalThis, key, { value: dom.window[key], configurable: true, writable: true });
}
globalThis.getComputedStyle = dom.window.getComputedStyle.bind(dom.window);
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
globalThis.EventSource = class {
  addEventListener() {}
  close() {}
};

process.on('exit', () => dom.window.close());
