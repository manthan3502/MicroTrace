import type { Span, Status } from './api';
import { duration, percent, serviceIdentity, utc } from './utils';
export function StatusBadge({ status }: { status: Status }) {
  return <span className={`status status-${status.toLowerCase()}`}>{status === 'OK' ? '✓' : '✕'} {status}</span>;
}
export function Service({ name }: { name: string }) {
  const [letter, tone] = serviceIdentity(name);
  return <span className={`service service-${tone}`}><span className="chip" aria-hidden="true">{letter}</span>{name}</span>;
}
export function ErrorMessage({ message, retry }: { message: string; retry?: () => void }) {
  return <div role="alert" className="notice error-notice">{message} {retry && <button onClick={retry}>Retry</button>}</div>;
}
export function SpanDetails({ span, total, spans, select }: {
  span: Span; total: number; spans: Span[]; select: (id: string) => void;
}) {
  const parent = spans.find(s => s.span_id === span.parent_span_id);
  return <aside className="span-details" aria-label="Span Details">
    <h2>Span Details</h2><h3 title={span.operation_name}>{span.operation_name}</h3>
    <Service name={span.service_name} />
    <p><span className="kind">{span.span_kind}</span> <StatusBadge status={span.status} /></p>
    {span.is_orphan && <p className="incomplete">◌ ORPHAN</p>}
    {span.status === 'ERROR' && <div className="notice error-notice"><strong>✕ ERROR</strong>
      <p>Type: {span.error_type ?? 'Unspecified'}</p><p>Message: {span.error_message ?? 'Operation failed'}</p></div>}
    <h3>Timing</h3>
    <dl><dt>Duration</dt><dd>{duration(span.duration_us)}</dd>
      {percent(span.duration_us, total) && <><dt>Percent of trace</dt><dd>{percent(span.duration_us, total)}</dd></>}
      <dt>Start offset</dt><dd>+{duration(span.start_offset_us)}</dd>
      <dt>Start time</dt><dd>{utc(span.start_time)}</dd><dt>End time</dt><dd>{utc(span.end_time)}</dd></dl>
    <h3>Attributes</h3>{Object.keys(span.attributes).length === 0 ? <p>No attributes.</p> :
      <dl>{Object.entries(span.attributes).sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) =>
        <div key={key}><dt>{key}</dt><dd>{String(value)}</dd></div>)}</dl>}
    <h3>Identifiers</h3><dl><dt>Trace ID</dt><dd>{span.trace_id}</dd><dt>Span ID</dt><dd>{span.span_id}</dd>
      <dt>Parent Span ID</dt><dd>{span.parent_span_id ?? 'none — root span'}</dd></dl>
    {span.parent_span_id && (parent ? <button onClick={() => select(parent.span_id)}>Select parent</button> :
      <p className="notice">Parent: not found in this trace</p>)}
  </aside>;
}
