export type RunConstraints = {
  max_change_pct?: number;
  category_floors?: Record<string, string>;
  category_ceilings?: Record<string, string>;
};

export type RunConstraintsDraft = {
  maxChangePct: string;
  categoryFloors: Record<string, string>;
  categoryCeilings: Record<string, string>;
};

export function emptyRunConstraints(): RunConstraintsDraft {
  return { maxChangePct: '', categoryFloors: {}, categoryCeilings: {} };
}

function money(value: string, label: string) {
  const text = value.trim();
  if (!/^\d{1,8}(?:\.\d{1,2})?$/.test(text) || Number(text) <= 0) {
    throw new Error(`${label} must be a positive price with at most two decimal places.`);
  }
  const [integer, fraction = ''] = text.split('.');
  return `${String(Number(integer))}.${fraction.padEnd(2, '0')}`;
}

export function serializeRunConstraints(draft: RunConstraintsDraft, categories: string[]): RunConstraints | undefined {
  const result: RunConstraints = {};
  const percent = draft.maxChangePct.trim();
  if (percent) {
    if (!/^(?:\d+(?:\.\d*)?|\.\d+)$/.test(percent) || !Number.isFinite(Number(percent)) || Number(percent) > 100) {
      throw new Error('Maximum price change must be between 0 and 100 percent.');
    }
    result.max_change_pct = Number(percent) / 100;
  }
  const floors: [string, string][] = [], ceilings: [string, string][] = [];
  for (const category of [...new Set(categories)]) {
    const floor = draft.categoryFloors[category]?.trim();
    const ceiling = draft.categoryCeilings[category]?.trim();
    const lower = floor ? money(floor, `${category} floor`) : undefined;
    const upper = ceiling ? money(ceiling, `${category} ceiling`) : undefined;
    if (lower && upper && Number(lower) > Number(upper)) {
      throw new Error(`${category} floor cannot exceed its ceiling.`);
    }
    if (lower) floors.push([category, lower]);
    if (upper) ceilings.push([category, upper]);
  }
  if (floors.length) result.category_floors = Object.fromEntries(floors);
  if (ceilings.length) result.category_ceilings = Object.fromEntries(ceilings);
  return Object.keys(result).length ? result : undefined;
}
