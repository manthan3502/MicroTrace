import type { Span } from './api';
export function duration(us: number): string {
  if (us < 1000) return `${Math.round(us)} µs`;
  if (us < 10000) return `${(us / 1000).toFixed(1)} ms`;
  if (us < 1000000) return `${Math.round(us / 1000)} ms`;
  return `${(us / 1000000).toFixed(2)} s`;
}
export function utc(value: string): string {
  return new Date(value).toISOString().replace('T', ' ').replace('Z', ' UTC');
}
export function scale(traceDuration: number, spans: Span[]): number {
  return Math.max(traceDuration, ...spans.map(s => s.start_offset_us + s.duration_us), 1);
}
export function geometry(span: Pick<Span, 'start_offset_us' | 'duration_us'>, total: number) {
  const left = Math.max(0, Math.min(100, span.start_offset_us / Math.max(total, 1) * 100));
  const width = Math.max(0, Math.min(100 - left, span.duration_us / Math.max(total, 1) * 100));
  return { left, width };
}
export function percent(us: number, total: number): string | null {
  return total > 0 ? `${Math.round(us / total * 100)}% of trace` : null;
}
export function ticks(total: number): number[] {
  const raw = Math.max(total, 1) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map(n => n * magnitude).find(n => n >= raw) ?? magnitude * 10;
  return Array.from({ length: Math.floor(total / step) + 1 }, (_, i) => i * step);
}
export interface Filters { service: string; status: string; min: string; offset: number }
export function readFilters(search: string): Filters {
  const p = new URLSearchParams(search);
  const offset = Number(p.get('offset') ?? 0);
  return { service: p.get('service') ?? '', status: p.get('status') ?? '',
    min: p.get('min_duration_ms') ?? '', offset: Number.isSafeInteger(offset) && offset >= 0 ? offset : 0 };
}
export function validMinimum(value: string): boolean {
  return value === '' || (/^\d+$/.test(value) && BigInt(value) <= 9223372036854775n);
}
export function filterQuery(f: Filters): string {
  const p = new URLSearchParams();
  if (f.service) p.set('service', f.service);
  if (f.status) p.set('status', f.status);
  if (f.min !== '') p.set('min_duration_ms', f.min);
  if (f.offset) p.set('offset', String(f.offset));
  return p.toString();
}
export function serviceIdentity(name: string) {
  const names: Record<string, [string, string]> = {
    'order-service': ['O', 'order'], 'payment-service': ['P', 'payment'],
    'notification-service': ['N', 'notification'],
  };
  return Object.hasOwn(names, name) ? names[name] : [name.slice(0, 1).toUpperCase(), 'other'];
}
