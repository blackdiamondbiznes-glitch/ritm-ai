/** One stroke icon set for the shell. Symbols live in the sprite at the top of index.html. */

/** Inline SVG that points at `#i-<name>`. Decorative: labels carry the meaning. */
export function icon(name, cls = "ic") {
  return `<svg class="${cls}" aria-hidden="true" focusable="false"><use href="#i-${name}"></use></svg>`;
}
