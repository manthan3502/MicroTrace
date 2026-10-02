import { Fragment, useState } from 'react';
import type { Detail } from './api';
import { ErrorMessage, Service, SpanDetails, StatusBadge } from './components';
import { duration, geometry, percent, scale, serviceIdentity, ticks, utc } from './utils';
import { useData } from './useData';

export default function TraceDetail({ traceId }: { traceId: string }) {
  const resource = useData<Detail>('/api/v1/traces/' + encodeURIComponent(traceId));
  const [selected, select] = useState<string | null>(null);
  const result = resource.data;
  const span = result?.spans.find(s => s.span_id === selected) ?? result?.spans[0];
  const desiredReturn = new URLSearchParams(window.location.search).get('returnTo');
  const back = desiredReturn === '/traces' || desiredReturn?.startsWith('/traces?') ? desiredReturn : '/traces';
  const total = result ? scale(result.trace.duration_us, result.spans) : 1;
  const firstOrphan = result?.spans.find(s => s.is_orphan)?.span_id;
  return <main>
    <a className="back" href={back}>← Back to traces</a>
    <div className="page-heading"><h1 className="trace-id">Trace {traceId}</h1>
      <button onClick={resource.refresh} disabled={resource.loading}>{resource.loading && result ? 'Refreshing…' : 'Refresh'}</button></div>
    {resource.loading && !result && <p role="status">Loading trace…</p>}
    {resource.error && <ErrorMessage message={resource.error} retry={resource.error === 'Trace not found.' ? undefined : resource.refresh} />}
    {result && <>
      <div className="trace-summary"><StatusBadge status={result.trace.status} /><strong>{duration(result.trace.duration_us)}</strong>
        <span>Started {utc(result.trace.start_time)}</span><span>{result.trace.span_count} spans · {result.trace.services.length} services</span>
        <span>{result.trace.root_operation}</span>
        {result.trace.status === 'ERROR' && <span>Error spans {result.spans.filter(s => s.status === 'ERROR').length} of {result.spans.length}</span>}
      </div>
      {result.trace.incomplete && <div className="notice" role="status">◌ Incomplete trace — some spans may be missing or still arriving.
        {result.orphan_span_ids.length > 0 && <p>{result.orphan_span_ids.length} span(s) reference a parent that is not currently stored.</p>}
        <button onClick={resource.refresh} disabled={resource.loading}>Refresh trace</button></div>}
      {result.spans.length === 0 ? <p>No span data is available.</p> : <div className="detail-layout">
        <section className="waterfall" aria-label="Trace waterfall" aria-busy={resource.loading}>
          <p className="legend">SERVER █ handles a request · CLIENT ▭ calls another service · INTERNAL ▄ local work</p>
          <div className="waterfall-scroll"><div className="waterfall-grid">
            <div className="waterfall-head"><span>Operation / Service</span><div className="axis">{ticks(total).map(t =>
              <span key={t} style={{ left: `${t / total * 100}%` }}>{duration(t)}</span>)}</div><span>Duration</span><span>Status</span></div>
            {result.spans.map(s => {
              const position = geometry(s, total);
              const [, tone] = serviceIdentity(s.service_name);
              return <Fragment key={s.span_id}>
                {s.span_id === firstOrphan && <p className="orphan-separator">Spans whose parent was not found</p>}
                <button className={`span-row ${span?.span_id === s.span_id ? 'selected' : ''} ${s.status === 'ERROR' ? 'error-row' : ''}`}
                  aria-label={`${s.service_name} ${s.operation_name} ${s.span_kind} ${s.status}`}
                  aria-pressed={span?.span_id === s.span_id} onClick={() => select(s.span_id)}>
                  <span className="span-identity" style={{ paddingLeft: Math.min(s.depth, 8) * 16 }}>
                    <strong title={s.operation_name}>{s.depth > 0 && <span aria-hidden="true">└ </span>}{s.operation_name}</strong>
                    <span><Service name={s.service_name} /> <span className="kind">{s.span_kind}</span></span>
                    {s.is_orphan && <span className="incomplete">◌ ORPHAN</span>}
                  </span>
                  <span className="timeline"><span className={`bar bar-${s.span_kind.toLowerCase()} service-${tone} ${s.status === 'ERROR' ? 'bar-error' : ''}`}
                    style={{ left: `clamp(0px, ${position.left}%, calc(100% - 3px))`, width: `max(3px, ${position.width}%)`, maxWidth: `max(3px, ${100 - position.left}%)` }}
                    title={`${s.service_name} · ${s.operation_name} · ${duration(s.duration_us)} · starts +${duration(s.start_offset_us)}`} /></span>
                  <span className="span-duration">{duration(s.duration_us)}{percent(s.duration_us, result.trace.duration_us) && <small>{percent(s.duration_us, result.trace.duration_us)}</small>}</span>
                  <StatusBadge status={s.status} />
                </button>
              </Fragment>;
            })}
          </div></div>
        </section>
        {span && <SpanDetails span={span} spans={result.spans} total={result.trace.duration_us} select={select} />}
      </div>}
    </>}
  </main>;
}
