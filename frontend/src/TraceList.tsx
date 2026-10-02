import { useEffect, useState } from 'react';
import type { Listing } from './api';
import { ErrorMessage, Service, StatusBadge } from './components';
import { duration, filterQuery, readFilters, utc, validMinimum } from './utils';
import type { Filters } from './utils';
import { useData } from './useData';

export default function TraceList() {
  const [applied, setApplied] = useState(() => readFilters(window.location.search));
  const [draft, setDraft] = useState(applied);
  const [validation, setValidation] = useState('');
  const query = filterQuery(applied);
  const valid = validMinimum(applied.min) && ['', 'OK', 'ERROR'].includes(applied.status);
  const listing = useData<Listing>(valid ? '/api/v1/traces?limit=50' + (query ? '&' + query : '') : null);
  const services = useData<{ services: string[] }>('/api/v1/services');
  useEffect(() => {
    function pop() { const next = readFilters(window.location.search); setApplied(next); setDraft(next); }
    window.addEventListener('popstate', pop);
    return () => window.removeEventListener('popstate', pop);
  }, []);
  function navigate(next: Filters) {
    const search = filterQuery(next);
    window.history.pushState(null, '', '/traces' + (search ? '?' + search : ''));
    setApplied(next); setDraft(next); setValidation('');
    if (filterQuery(next) === query) listing.refresh();
  }
  const items = listing.data?.items ?? [];
  const hasFilters = !!(applied.service || applied.status || applied.min);
  const returnTo = '/traces' + (query ? '?' + query : '');
  return <main>
    <div className="page-heading"><h1>Traces</h1><button disabled={listing.loading} onClick={listing.refresh}>{listing.loading && listing.data ? 'Refreshing…' : 'Refresh'}</button></div>
    <form className="filters" onSubmit={e => {
      e.preventDefault();
      if (!validMinimum(draft.min)) { setValidation('Enter an integer duration of 0 or more.'); return; }
      navigate({ ...draft, offset: 0 });
    }}>
      <label>Service<select aria-label="Service" value={draft.service} disabled={!!services.error} onChange={e => setDraft({ ...draft, service: e.target.value })}>
        <option value="">All services</option>
        {services.data?.services.map(name => <option key={name}>{name}</option>)}
      </select>{services.error && <small>Services unavailable</small>}</label>
      <label>Status<select value={draft.status} onChange={e => setDraft({ ...draft, status: e.target.value })}>
        <option value="">All</option><option>OK</option><option>ERROR</option></select></label>
      <label>Min duration (ms)<input aria-describedby="duration-validation" type="text" inputMode="numeric" value={draft.min} onChange={e => setDraft({ ...draft, min: e.target.value })} /></label>
      <button type="submit">Apply</button><button type="button" onClick={() => navigate({ service: '', status: '', min: '', offset: 0 })}>Reset</button>
      {(validation || !valid) && <p id="duration-validation" role="alert">{validation || 'Invalid URL filters. Reset filters to continue.'}</p>}
    </form>
    {listing.error && <ErrorMessage message={listing.error} retry={listing.refresh} />}
    {listing.loading && !listing.data && valid && <p role="status">Loading traces…</p>}
    {!listing.loading && !listing.error && valid && items.length === 0 && <div className="empty">
      <h2>{applied.offset ? 'No more traces.' : hasFilters ? 'No traces match these filters.' : 'No traces yet.'}</h2>
      {hasFilters && !applied.offset ? <button onClick={() => navigate({ service: '', status: '', min: '', offset: 0 })}>Clear filters</button> : !applied.offset && <p>Generate one with: <code>python scripts/demo.py healthy</code></p>}
    </div>}
    {items.length > 0 && <div className="table-scroll" aria-busy={listing.loading}><table>
      <thead><tr>{['Status', 'Start (UTC)', 'Root Operation', 'Duration', 'Services', 'Spans', 'Trace ID'].map(c => <th key={c} scope="col">{c}</th>)}</tr></thead>
      <tbody>{items.map(trace => {
        const href = '/traces/' + trace.trace_id + '?returnTo=' + encodeURIComponent(returnTo);
        return <tr key={trace.trace_id} onClick={e => { if (!(e.target instanceof Element && e.target.closest('a'))) window.location.assign(href); }}>
          <td><StatusBadge status={trace.status} />{trace.incomplete && <span className="incomplete">◌ INCOMPLETE</span>}</td>
          <td className="technical">{utc(trace.start_time)}</td>
          <td><a href={href}>{trace.root_operation}</a></td>
          <td className="number">{duration(trace.duration_us)}</td>
          <td><span className="list-services">{trace.services.map(name => <Service key={name} name={name} />)}</span></td>
          <td className="number">{trace.span_count}</td>
          <td className="technical" title={trace.trace_id}>{trace.trace_id.slice(0, 8)}…{trace.trace_id.slice(-5)}</td>
        </tr>;
      })}</tbody>
    </table></div>}
    <div className="pagination"><span>{items.length ? `Showing ${applied.offset + 1}–${applied.offset + items.length}` : ''}</span><div>
      <button disabled={listing.loading || applied.offset === 0} onClick={() => navigate({ ...applied, offset: Math.max(0, applied.offset - 50) })}>Previous</button>
      <button disabled={listing.loading || items.length !== 50} onClick={() => navigate({ ...applied, offset: applied.offset + 50 })}>Next</button></div></div>
  </main>;
}
