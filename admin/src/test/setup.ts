/**
 * Vitest setup — jest-dom matchers + the CSS/style shims jsdom lacks.
 * Loaded via the `test` block in vite.config.ts.
 */

import "@testing-library/jest-dom/vitest";

// jsdom does not implement matchMedia — theme/media-query code calls it.
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: () => undefined,
      removeEventListener: () => undefined,
      dispatchEvent: () => false,
    }) as unknown as MediaQueryList;
}

// jsdom lacks scrollTo; the Drawer/loops never need the real behavior in tests.
if (typeof window.scrollTo !== "function") {
  window.scrollTo = () => undefined;
}
