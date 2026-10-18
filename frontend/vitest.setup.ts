// jsdom has no PointerEvent — testing-library then falls back to window.Event,
// which drops clientX/button from the init dict. MouseEvent keeps both, so the
// polyfill only needs to exist by name for createEvent's constructor lookup.
if (!window.PointerEvent) {
  const PointerEventShim = class PointerEvent extends MouseEvent {};
  window.PointerEvent = PointerEventShim as unknown as typeof PointerEvent;
}
