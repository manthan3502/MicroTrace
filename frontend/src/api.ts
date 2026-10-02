export type Status = 'OK' | 'ERROR';
export type Kind = 'SERVER' | 'CLIENT' | 'INTERNAL';
export interface Trace {
  trace_id: string; root_operation: string; start_time: string; duration_us: number;
  status: Status; services: string[]; span_count: number; incomplete: boolean;
}
export interface Span {
  trace_id: string; span_id: string; parent_span_id: string | null;
  service_name: string; operation_name: string; span_kind: Kind; status: Status;
  start_time: string; end_time: string; duration_us: number; start_offset_us: number;
  depth: number; is_orphan: boolean; error_type: string | null; error_message: string | null;
  attributes: Record<string, string | number | boolean | null>;
}
export interface Detail { trace: Trace; spans: Span[]; orphan_span_ids: string[] }
export interface Listing { items: Trace[]; limit: number; offset: number }
export class ApiError extends Error {
  status: number;
  constructor(status: number) {
    super(status === 404 || status === 422 ? 'Trace not found.' : 'The backend returned an error.');
    this.status = status;
  }
}
export async function getJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  let response: Response;
  try { response = await fetch(path, { signal }); }
  catch (error) {
    if (signal?.aborted) throw error;
    throw new Error("Can't reach the MicroTrace backend.");
  }
  if (!response.ok) throw new ApiError(response.status);
  return response.json() as Promise<T>;
}
