import "@testing-library/jest-dom/vitest";

// jsdom has no layout engine and no scrollIntoView; the message list calls it on stream.
Element.prototype.scrollIntoView ??= () => {};
