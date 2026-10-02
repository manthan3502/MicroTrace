import { describe, expect, it } from 'vitest';
import { duration, filterQuery, geometry, percent, readFilters, scale, serviceIdentity, ticks, utc, validMinimum } from './utils';
import { root } from './test/fixtures';
describe('approved formatting and waterfall geometry', () => {
  it.each(['constructor', 'toString', '__proto__', 'custom-service'])('falls back safely for service %s', name => {
    expect(serviceIdentity(name)).toEqual([name.slice(0, 1).toUpperCase(), 'other']);
  });
  it('preserves the approved known service identities', () => {
    expect(serviceIdentity('order-service')).toEqual(['O', 'order']);
    expect(serviceIdentity('payment-service')).toEqual(['P', 'payment']);
    expect(serviceIdentity('notification-service')).toEqual(['N', 'notification']);
  });
  it.each([[640, '640 µs'], [4200, '4.2 ms'], [135000, '135 ms'], [1240000, '1.24 s'], [0, '0 µs']])('formats %i', (value, expected) => {
    expect(duration(value as number)).toBe(expected);
  });
  it('renders absolute UTC', () => expect(utc('2026-10-02T01:00:00Z')).toBe('2026-10-02 01:00:00.000 UTC'));
  it('extends scale for spans beyond root and protects zero', () => {
    expect(scale(1, [{ ...root, start_offset_us: 10, duration_us: 20 }])).toBe(30);
    expect(scale(0, [])).toBe(1);
  });
  it('computes and clamps positions', () => {
    expect(geometry({ start_offset_us: 25, duration_us: 50 }, 100)).toEqual({ left: 25, width: 50 });
    expect(geometry({ start_offset_us: 90, duration_us: 50 }, 100)).toEqual({ left: 90, width: 10 });
    expect(geometry({ start_offset_us: -10, duration_us: 0 }, 0)).toEqual({ left: 0, width: 0 });
  });
  it('produces readable ticks and percentage with zero safety', () => {
    expect(ticks(920000)).toEqual([0, 250000, 500000, 750000]);
    expect(ticks(0)).toEqual([0]);
    expect(percent(800000, 920000)).toBe('87% of trace');
    expect(percent(1, 0)).toBeNull();
  });
  it('keeps filter URL round trips and enforces integer duration', () => {
    const f = readFilters('?service=payment-service&status=ERROR&min_duration_ms=500&offset=50');
    expect(filterQuery(f)).toBe('service=payment-service&status=ERROR&min_duration_ms=500&offset=50');
    for (const v of ['', '0', '500']) expect(validMinimum(v)).toBe(true);
    for (const v of ['-1', '1.2', 'NaN', 'abc', '999999999999999999']) expect(validMinimum(v)).toBe(false);
    expect(readFilters('?offset=-1').offset).toBe(0);
  });
});
