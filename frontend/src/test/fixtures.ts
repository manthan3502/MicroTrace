import type { Detail, Span, Trace } from '../api';
export const id = 'a'.repeat(32);
export const trace: Trace = { trace_id: id, root_operation: 'POST /orders',
  start_time: '2026-10-02T01:00:00Z', duration_us: 900000, status: 'OK',
  services: ['order-service', 'payment-service'], span_count: 3, incomplete: false };
export const root: Span = { trace_id: id, span_id: '1'.repeat(16), parent_span_id: null,
  service_name: 'order-service', operation_name: 'POST /orders', span_kind: 'SERVER',
  status: 'OK', start_time: trace.start_time, end_time: '2026-10-02T01:00:00.900Z',
  duration_us: 900000, start_offset_us: 0, depth: 0, is_orphan: false, error_type: null,
  error_message: null, attributes: {} };
export const client: Span = { ...root, span_id: '2'.repeat(16), parent_span_id: root.span_id,
  operation_name: 'POST payment-service /charge', span_kind: 'CLIENT', duration_us: 800000,
  start_offset_us: 10000, depth: 1 };
export const internal: Span = { ...client, span_id: '3'.repeat(16), parent_span_id: client.span_id,
  operation_name: 'process-payment', span_kind: 'INTERNAL', service_name: 'payment-service',
  duration_us: 780000, start_offset_us: 20000, depth: 2, attributes: { 'demo.scenario': 'normal' } };
export const detail: Detail = { trace, spans: [root, client, internal], orphan_span_ids: [] };
export function response(value: unknown, status = 200): Response {
  return { ok: status >= 200 && status < 300, status, json: async () => value } as Response;
}
