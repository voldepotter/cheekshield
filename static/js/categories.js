/**
 * CheekShield AI — Category Registry (Section 6.8)
 *
 * Single source of truth for categories. Never hard-code categories anywhere else.
 */

export const CATEGORY_REGISTRY = [
  {
    name: 'Urgency',
    glyph: 'glyph-urgency',
    short: 'Artificial time pressure or countdown timers',
    kind: 'model',
  },
  {
    name: 'Scarcity',
    glyph: 'glyph-scarcity',
    short: 'Claims of limited stock or high demand',
    kind: 'model',
  },
  {
    name: 'Social Proof',
    glyph: 'glyph-social-proof',
    short: 'Real-time viewer counts or popularity pressure',
    kind: 'model',
  },
  {
    name: 'Misdirection',
    glyph: 'glyph-misdirection',
    short: 'Visual asymmetry, deceptive styling, or confirm-shaming',
    kind: 'both',
  },
  {
    name: 'Preselected Choice',
    glyph: 'glyph-preselected-choice',
    short: 'Pre-ticked add-ons, warranties, or opt-ins',
    kind: 'rule',
  },
  {
    name: 'Disguised Ad',
    glyph: 'glyph-disguised-ad',
    short: 'Promotions formatted to look like content or navigation',
    kind: 'rule',
  },
  {
    name: 'Other Dark Pattern',
    glyph: 'glyph-other',
    short: 'Other manipulative or deceptive design patterns',
    kind: 'model',
  },
];

export const FALLBACK_CATEGORY = {
  name: 'Unknown',
  glyph: 'glyph-fallback',
  short: 'Unclassified pattern detected by engine',
  kind: 'model',
};

/**
 * Find category metadata by name, with safe fallback for unknown categories.
 */
export function getCategoryInfo(name) {
  if (!name) return { ...FALLBACK_CATEGORY };
  const found = CATEGORY_REGISTRY.find(
    (c) => c.name.toLowerCase() === name.toLowerCase()
  );
  if (found) return found;
  return {
    name,
    glyph: FALLBACK_CATEGORY.glyph,
    short: `Flagged as ${name}`,
    kind: 'model',
  };
}

/**
 * Get ordered list of all categories to display in the receipt tally or filters,
 * appending any active unknown categories alphabetically.
 */
export function getAllDisplayCategories(extraCategories = []) {
  const knownNames = new Set(CATEGORY_REGISTRY.map((c) => c.name.toLowerCase()));
  const extras = [];

  for (const cat of extraCategories) {
    if (cat && !knownNames.has(cat.toLowerCase())) {
      knownNames.add(cat.toLowerCase());
      extras.push(getCategoryInfo(cat));
    }
  }

  extras.sort((a, b) => a.name.localeCompare(b.name));
  return [...CATEGORY_REGISTRY, ...extras];
}
