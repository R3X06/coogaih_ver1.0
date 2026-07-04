// ---------------------------------------------------------------------------
// Coogaih — shared categorization core
//
// Runs INSIDE each producer, PRE-EGRESS. The raw signal (url, title, window
// title) is seen here, on-device; only the returned CategoryDecision is
// allowed to cross the wire. This file is the single categorization brain —
// every producer maps its surface into a SignalBundle and calls categorize().
//
// The core is PURE and SYNCHRONOUS: no I/O, no browser APIs, no LLM, no clock.
// Same (signal, ruleset) always yields the same decision. That is what makes
// it property-testable (friend's job) and portable to a Python watcher later.
//
// Tier 3 (LLM inference) is deliberately NOT in the core — it's async and
// opt-in. The caller handles it when a decision comes back tier==='unknown'.
// ---------------------------------------------------------------------------

export type Category = 'study' | 'work' | 'distraction' | 'neutral' | 'unknown';

export type SignalTier =
  | 'container'      // Tier 0: domain / app identity
  | 'identifier'     // Tier 1: url path / page title / window title / channel
  | 'platform_meta'  // Tier 2: og:type, schema.org, platform's own category
  | 'inferred'       // Tier 3: LLM (set by caller, never by the core)
  | 'user_confirmed' // resolved from a user-confirmed rule
  | 'unknown';       // no signal resolved it

// --- Producer-agnostic input -----------------------------------------------
// Every surface (browser tab, native window, media player, mobile later)
// collapses to this. Producers differ only in which fields they can fill.
export interface SignalBundle {
  container: { type: 'domain' | 'app'; value: string }; // ALWAYS present
  identifier?: {
    urlPath?: string; // path + query, browser only
    title?: string;   // page title OR window title — same field on purpose
    channel?: string; // creator/author where cheaply available
  };
  platformMeta?: {
    ogType?: string;
    schemaType?: string;
    platformCategory?: string; // e.g. YouTube's own "Education"
  };
}

// --- Output ----------------------------------------------------------------
export interface CategoryDecision {
  category: Category;
  confidence: number;   // 0..1
  tier: SignalTier;
  source: string;       // which rule/mechanism fired — audit trail
  needsReview: boolean; // route to the batch review UI to become a real rule
}

// --- Ruleset ---------------------------------------------------------------
export interface ContainerRule {
  category?: Category;         // required when singular
  singular?: boolean;          // Tier 0 is terminal — never escalate
  polymorphic?: boolean;       // Tier 0 is NOT terminal — must consult higher tiers
  fallbackCategory?: Category; // used when polymorphic AND no higher signal fires
  fallbackConfidence?: number;
  confidence?: number;         // override the default for a singular match
}

export interface IdentifierRule {
  container?: string;  // scope to one container; omit = applies to ANY container
  titleRegex?: string;
  pathRegex?: string;
  channelIn?: string[];
  ci?: boolean;        // case-insensitive match. Use THIS, never inline (?i) —
                       // (?i) is PCRE/Python syntax and is INVALID in JS RegExp.
  category: Category;
  confidence?: number;
  source?: string;
}

export interface PlatformMetaRule {
  container?: string;
  ogType?: string;
  schemaType?: string;
  platformCategory?: string;
  category: Category;
  confidence?: number;
  source?: string;
}

export interface Ruleset {
  version: number;
  defaultCategory: Category;
  exclusions: string[]; // containers that must NEVER be recorded at all
  containers: Record<string, ContainerRule>;
  identifierRules: IdentifierRule[];
  platformMetaRules: PlatformMetaRule[];
}

// --- Tunable confidence constants ------------------------------------------
// Starting values, not gospel — same spirit as SWITCH_MAX / FRAG_MAX. Sanity-
// check against real captured sessions and adjust. Whoever changes them tells
// the other side, because the engine's down-weighting thresholds assume them.
export const TIER_CONFIDENCE = {
  container_singular: 0.95,
  identifier: 0.8,
  platform_meta: 0.85,
  polymorphic_fallback: 0.4,
  default_fallthrough: 0.2, // unknown container, best-guess default bucket
  user_confirmed: 1.0,
} as const;

// Sentinel source the caller checks to DROP an event entirely (exclusion list).
export const EXCLUDED_SOURCE = 'exclusion';

// ---------------------------------------------------------------------------
// The cascade. Cheapest / most certain tier that resolves confidently wins.
// ---------------------------------------------------------------------------
export function categorize(signal: SignalBundle, ruleset: Ruleset): CategoryDecision {
  const key = signal.container.value;

  // Exclusion short-circuit — caller sees EXCLUDED_SOURCE and drops the event.
  if (ruleset.exclusions.includes(key)) {
    return { category: 'neutral', confidence: 0, tier: 'unknown', source: EXCLUDED_SOURCE, needsReview: false };
  }

  const containerRule = ruleset.containers[key];

  // Tier 0 — container identity. Terminal only for SINGULAR containers.
  if (containerRule?.singular && containerRule.category) {
    return {
      category: containerRule.category,
      confidence: containerRule.confidence ?? TIER_CONFIDENCE.container_singular,
      tier: 'container',
      source: `container:${key}`,
      needsReview: false,
    };
  }

  // Tier 1 — within-container identifier (path / title / channel).
  const idMatch = matchIdentifier(signal, ruleset, key);
  if (idMatch) return idMatch;

  // Tier 2 — platform semantic metadata.
  const metaMatch = matchPlatformMeta(signal, ruleset, key);
  if (metaMatch) return metaMatch;

  // Tier 3 — inference is NOT run here (async + opt-in). Caller handles it on
  // tier === 'unknown'. See runInferenceIfAllowed() sketch below.

  // Fallthrough for a KNOWN-but-polymorphic container with no higher signal:
  // emit its best-guess fallback at low confidence, flagged for review.
  if (containerRule?.polymorphic && containerRule.fallbackCategory) {
    return {
      category: containerRule.fallbackCategory,
      confidence: containerRule.fallbackConfidence ?? TIER_CONFIDENCE.polymorphic_fallback,
      tier: 'container',
      source: `polymorphic_fallback:${key}`,
      needsReview: true,
    };
  }

  // Fallthrough for a wholly UNKNOWN container: bucket under the default so the
  // time-on-task isn't lost, but tier=unknown + low confidence tells the engine
  // to exclude it from clean metrics, and needsReview promotes it to a real rule.
  return {
    category: ruleset.defaultCategory,
    confidence: TIER_CONFIDENCE.default_fallthrough,
    tier: 'unknown',
    source: 'default',
    needsReview: true,
  };
}

// --- Tier 1 matcher --------------------------------------------------------
function matchIdentifier(signal: SignalBundle, ruleset: Ruleset, key: string): CategoryDecision | null {
  const id = signal.identifier;
  if (!id) return null;

  for (const rule of ruleset.identifierRules) {
    if (rule.container && rule.container !== key) continue;

    const hasClause = !!(rule.channelIn || rule.titleRegex || rule.pathRegex);
    if (!hasClause) continue; // an all-null rule is invalid; never let it match

    if (rule.channelIn && (!id.channel || !rule.channelIn.includes(id.channel))) continue;
    if (rule.titleRegex && (!id.title || !safeTest(rule.titleRegex, id.title, rule.ci))) continue;
    if (rule.pathRegex && (!id.urlPath || !safeTest(rule.pathRegex, id.urlPath, rule.ci))) continue;

    return {
      category: rule.category,
      confidence: rule.confidence ?? TIER_CONFIDENCE.identifier,
      tier: 'identifier',
      source: rule.source ?? `identifier:${rule.titleRegex ?? rule.pathRegex ?? 'channel'}`,
      needsReview: false,
    };
  }
  return null;
}

// --- Tier 2 matcher --------------------------------------------------------
function matchPlatformMeta(signal: SignalBundle, ruleset: Ruleset, key: string): CategoryDecision | null {
  const meta = signal.platformMeta;
  if (!meta) return null;

  for (const rule of ruleset.platformMetaRules) {
    if (rule.container && rule.container !== key) continue;

    const hasClause = !!(rule.platformCategory || rule.ogType || rule.schemaType);
    if (!hasClause) continue;

    if (rule.platformCategory && meta.platformCategory !== rule.platformCategory) continue;
    if (rule.ogType && meta.ogType !== rule.ogType) continue;
    if (rule.schemaType && meta.schemaType !== rule.schemaType) continue;

    return {
      category: rule.category,
      confidence: rule.confidence ?? TIER_CONFIDENCE.platform_meta,
      tier: 'platform_meta',
      source: rule.source ?? `platform_meta:${key}`,
      needsReview: false,
    };
  }
  return null;
}

// --- Safe, cached regex ----------------------------------------------------
// Memoized compile keeps recompute cheap; input is length-capped to bound
// pathological regex cost. Cache is pure memoization — it never changes output.
const _regexCache = new Map<string, RegExp | null>();
function compile(pattern: string, ci?: boolean): RegExp | null {
  const cacheKey = (ci ? 'i:' : '') + pattern;
  const cached = _regexCache.get(cacheKey);
  if (cached !== undefined) return cached;
  let re: RegExp | null;
  try { re = new RegExp(pattern, ci ? 'i' : ''); } catch { re = null; }
  _regexCache.set(cacheKey, re);
  return re;
}
function safeTest(pattern: string, input: string, ci?: boolean): boolean {
  const re = compile(pattern, ci);
  if (!re) return false; // a malformed rule never matches, never throws
  return re.test(input.length > 512 ? input.slice(0, 512) : input);
}

// ---------------------------------------------------------------------------
// Tier 3 seam (NOT part of the pure core). Illustrates the caller contract.
// ---------------------------------------------------------------------------
export interface InferenceCache {
  get(key: string): CategoryDecision | undefined;
  set(key: string, value: CategoryDecision): void;
}

export function inferenceCacheKey(signal: SignalBundle): string {
  const t = signal.identifier?.title ?? '';
  return `${signal.container.value}::${t}`;
}

// Sketch — how a producer wraps the pure core with opt-in inference.
// telemetryLevel comes from the user's setting (schema.sql `telemetry_level`).
//
//   const decision = categorize(signal, ruleset);
//   if (decision.tier !== 'unknown') return decision;
//   if (telemetryLevel !== 'enhanced_titles_optional') return decision; // stay unknown
//   const ck = inferenceCacheKey(signal);
//   const hit = cache.get(ck);
//   if (hit) return hit;
//   const inferred = await runInference(signal);      // LLM, opt-in only
//   const proposed: CategoryDecision = { ...inferred, tier: 'inferred', needsReview: true };
//   cache.set(ck, proposed);                           // classify each item once, ever
//   return proposed;                                   // shown as a rule the user confirms

// ---------------------------------------------------------------------------
// Producer adapters — the universality payoff. Every surface → same bundle.
// ---------------------------------------------------------------------------
export function bundleFromBrowserTab(input: {
  url: string;
  title: string;
  channel?: string;
  ogType?: string;
  platformCategory?: string;
}): SignalBundle {
  const u = new URL(input.url);
  return {
    container: { type: 'domain', value: u.hostname.replace(/^www\./, '') },
    identifier: { urlPath: u.pathname + u.search, title: input.title, channel: input.channel },
    platformMeta: { ogType: input.ogType, platformCategory: input.platformCategory },
  };
}

// The native YouTube app leaks the video title into the OS window title, so the
// SAME titleRegex identifier rules fire here — no URL needed. That is the whole
// point: the app and the website resolve through one code path.
export function bundleFromWindow(input: { app: string; windowTitle: string }): SignalBundle {
  return {
    container: { type: 'app', value: input.app },
    identifier: { title: input.windowTitle },
  };
}

// ---------------------------------------------------------------------------
// Example ruleset — illustrative + a ready fixture for the friend's tests.
// ---------------------------------------------------------------------------
export const EXAMPLE_RULESET: Ruleset = {
  version: 2,
  defaultCategory: 'neutral',
  exclusions: ['Banking', 'Messages', 'chase.com'],
  containers: {
    // Singular — Tier 0 terminal
    'leetcode.com': { singular: true, category: 'study' },
    'coursera.org': { singular: true, category: 'study' },
    'Code': { singular: true, category: 'study' },
    'Slack': { singular: true, category: 'work' },
    'Mail': { singular: true, category: 'work' },
    // Polymorphic — must consult higher tiers; falls back to distraction
    'youtube.com': { polymorphic: true, fallbackCategory: 'distraction' },
    'YouTube': { polymorphic: true, fallbackCategory: 'distraction' },
  },
  identifierRules: [
    // Channel allowlist beats regex — near-zero false positives
    { container: 'youtube.com', channelIn: ['3Blue1Brown', 'MIT OpenCourseWare'], category: 'study', confidence: 0.95 },
    { channelIn: ['3Blue1Brown', 'MIT OpenCourseWare'], category: 'study', confidence: 0.95 }, // app surface (no container scope)
    // Title regex — applies to any polymorphic/unknown container that carries a title
    { titleRegex: '(lecture|tutorial|course|derivation|proof)', ci: true, category: 'study' },
  ],
  platformMetaRules: [
    { container: 'youtube.com', platformCategory: 'Education', category: 'study', confidence: 0.85 },
  ],
};
