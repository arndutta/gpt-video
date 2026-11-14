import { JSDOM } from 'jsdom';

// This is a DOM event environment, not a real browser or layout engine.
const dom = new JSDOM('<!doctype html><html><body></body></html>', {
  url: 'http://127.0.0.1:5173/', pretendToBeVisual: true,
});
// CSSOM identifier serialization: jsdom omits the browser API used by native
// radio-key traversal in user-event. This supplies escaping, not keyboard behavior.
function escapeIdentifier(value) {
  if (!arguments.length) throw new TypeError('CSS.escape requires an argument.');
  const text = String(value);
  let result = '';
  for (let index = 0; index < text.length; index++) {
    const code = text.charCodeAt(index), char = text[index];
    if (code === 0) result += '\uFFFD';
    else if ((code >= 1 && code <= 31) || code === 127 ||
      (index === 0 && code >= 48 && code <= 57) ||
      (index === 1 && code >= 48 && code <= 57 && text[0] === '-')) {
      result += '\\' + code.toString(16) + ' ';
    } else if (index === 0 && char === '-' && text.length === 1) result += '\\-';
    else if (code >= 128 || char === '-' || char === '_' ||
      (code >= 48 && code <= 57) || (code >= 65 && code <= 90) ||
      (code >= 97 && code <= 122)) result += char;
    else result += '\\' + char;
  }
  return result;
}
dom.window.CSS ??= {};
dom.window.CSS.escape ??= escapeIdentifier;
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
