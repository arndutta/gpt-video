// Native Tab stops for modal boundaries. Geometry is deliberately not used:
// visually hidden radio inputs remain operable, and DOM tests have no layout.
const candidates = 'a[href], area[href], button, input, select, textarea, summary, iframe, audio[controls], video[controls], [tabindex], [contenteditable]';

function firstSummary(details: Element): Element | undefined {
  return Array.from(details.children).find(child => child.tagName === 'SUMMARY');
}

function tabOrder(element: HTMLElement): number {
  if (element.hasAttribute('tabindex')) return element.tabIndex;
  if (element.tagName === 'SUMMARY') {
    const details = element.parentElement;
    return details?.tagName === 'DETAILS' && firstSummary(details) === element ? 0 : -1;
  }
  if (element.matches('audio[controls], video[controls]')) return 0;
  if (element.hasAttribute('contenteditable') && element.getAttribute('contenteditable') !== 'false') {
    // Nested editable regions are not separate Tab stops without tabindex.
    return element.parentElement?.closest('[contenteditable]:not([contenteditable="false"])') ? -1 : 0;
  }
  return element.tabIndex;
}

function available(element: HTMLElement): boolean {
  if (tabOrder(element) < 0 || element.matches(':disabled, input[type="hidden"]')) return false;
  if (element.closest('[hidden], [inert]')) return false;
  const view = element.ownerDocument.defaultView;
  if (!view) return false;
  // Visibility inherits, but an explicit visible descendant can override it.
  const visibility = view.getComputedStyle(element).visibility;
  if (visibility === 'hidden' || visibility === 'collapse') return false;
  for (let ancestor: HTMLElement | null = element; ancestor; ancestor = ancestor.parentElement) {
    if (view.getComputedStyle(ancestor).display === 'none') return false;
    if (ancestor !== element && ancestor.tagName === 'DETAILS' && !ancestor.hasAttribute('open')) {
      if (!firstSummary(ancestor)?.contains(element)) return false;
    }
  }
  return true;
}

function radioTabStop(radio: HTMLInputElement): boolean {
  if (!radio.name) return true;
  const tree = radio.getRootNode() as Document | ShadowRoot;
  const group = Array.from(tree.querySelectorAll<HTMLInputElement>('input[type="radio"]'))
    .filter(other => other.name === radio.name && other.form === radio.form && available(other));
  // A checked radio outside this modal is still part of the native radio group.
  return (group.find(other => other.checked) || group[0]) === radio;
}

export function focusableElements(root: HTMLElement): HTMLElement[] {
  return Array.from(root.querySelectorAll<HTMLElement>(candidates))
    .filter(element => available(element) && (!element.matches('input[type="radio"]') || radioTabStop(element as HTMLInputElement)))
    .map((element, index) => ({ element, index, order: tabOrder(element) }))
    .sort((left, right) => {
      const leftOrder = left.order > 0 ? left.order : Infinity;
      const rightOrder = right.order > 0 ? right.order : Infinity;
      return leftOrder - rightOrder || left.index - right.index;
    })
    .map(item => item.element);
}
