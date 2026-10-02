import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TraceDetail from './TraceDetail';
import App from './App';
import { client, detail, id, internal, response, root } from './test/fixtures';

beforeEach(() => {
  window.history.replaceState(null, '', '/traces/' + id);
  vi.stubGlobal('fetch', vi.fn(async () => response(detail)));
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function panel() { return screen.getByRole('complementary', { name: 'Span Details' }); }
describe('Trace Detail', () => {
  it.each(['constructor', 'toString', '__proto__', 'custom-service'])('renders unknown service %s in rows and details', async name => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...detail,
      trace: { ...detail.trace, services: [name], span_count: 1 }, spans: [{ ...root, service_name: name }] })));
    render(<TraceDetail traceId={id} />);
    const row = await screen.findByRole('button', { name: `${name} POST /orders SERVER OK` });
    expect(row.querySelector('.service-other')).toHaveTextContent(name);
    expect(within(panel()).getByText(name)).toBeInTheDocument();
  });
  it('uses displayed non-quarter ticks for every row gridline', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...detail,
      trace: { ...detail.trace, duration_us: 920000 } })));
    render(<TraceDetail traceId={id} />);
    await screen.findByRole('complementary');
    const anchors = [...document.querySelectorAll<HTMLElement>('.axis-tick')];
    expect(anchors.map(t => t.textContent)).toEqual(['0 µs', '250 ms', '500 ms', '750 ms']);
    const expected = [0, 250000, 500000, 750000].map(t => t / 920000 * 100);
    expect(anchors.map(t => parseFloat(t.style.left))).toEqual(expected);
    for (const timeline of document.querySelectorAll('.timeline')) {
      const lines = [...timeline.querySelectorAll<HTMLElement>('.timeline-gridline')];
      expect(lines.map(t => parseFloat(t.style.left))).toEqual(expected);
      expect(lines.every(t => t.getAttribute('aria-hidden') === 'true')).toBe(true);
    }
  });
  it('renders API ordering, first selection, badges, shapes and depth', async () => {
    render(<TraceDetail traceId={id} />);
    const rows = await screen.findAllByRole('button', { pressed: true });
    expect(rows[0]).toHaveAccessibleName('order-service POST /orders SERVER OK');
    const waterfall = screen.getByRole('region', { name: 'Trace waterfall' });
    const all = within(waterfall).getAllByRole('button');
    expect(all.map(r => r.getAttribute('aria-label'))).toEqual([
      'order-service POST /orders SERVER OK', 'order-service POST payment-service /charge CLIENT OK', 'payment-service process-payment INTERNAL OK',
    ]);
    expect(waterfall.querySelectorAll('.bar-server')).toHaveLength(1);
    expect(waterfall.querySelectorAll('.bar-client')).toHaveLength(1);
    expect(waterfall.querySelectorAll('.bar-internal')).toHaveLength(1);
    expect(waterfall.querySelectorAll('.span-identity')[2]).toHaveStyle({ paddingLeft: '32px' });
    expect(within(panel()).getByText(root.span_id)).toBeInTheDocument();
  });
  it('selects spans and navigates to parent', async () => {
    render(<TraceDetail traceId={id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'payment-service process-payment INTERNAL OK' }));
    expect(within(panel()).getByText('demo.scenario')).toBeInTheDocument();
    fireEvent.click(within(panel()).getByText('Select parent'));
    expect(within(panel()).getByText(client.span_id)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'order-service POST payment-service /charge CLIENT OK' })).toHaveAttribute('aria-pressed', 'true');
  });
  it('renders ERROR with text, tint and stripe class, plus error details', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      ...detail, trace: { ...detail.trace, status: 'ERROR' },
      spans: [{ ...internal, status: 'ERROR', error_type: 'InjectedPaymentError', error_message: 'Operation failed' }],
    })));
    render(<TraceDetail traceId={id} />);
    const row = await screen.findByRole('button', { name: 'payment-service process-payment INTERNAL ERROR' });
    expect(row).toHaveClass('error-row');
    expect(row.querySelector('.bar')).toHaveClass('bar-error');
    expect(within(panel()).getByText('Type: InjectedPaymentError')).toBeInTheDocument();
    expect(screen.getByText('Error spans 1 of 1')).toBeInTheDocument();
  });
  it('preserves orphan subtree depth and exposes missing parent', async () => {
    const orphan = { ...client, parent_span_id: 'f'.repeat(16), depth: 0, is_orphan: true };
    vi.stubGlobal('fetch', vi.fn(async () => response({
      ...detail, trace: { ...detail.trace, incomplete: true },
      spans: [root, orphan, { ...internal, depth: 1 }], orphan_span_ids: [client.span_id],
    })));
    render(<TraceDetail traceId={id} />);
    expect(await screen.findByText(/Incomplete trace —/)).toBeInTheDocument();
    expect(screen.getByText('Spans whose parent was not found')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'order-service POST payment-service /charge CLIENT OK' }));
    expect(within(panel()).getByText('Parent: not found in this trace')).toBeInTheDocument();
  });
  it('keeps selected span on refresh, falls back when missing', async () => {
    let data = detail;
    vi.stubGlobal('fetch', vi.fn(async () => response(data)));
    render(<TraceDetail traceId={id} />);
    fireEvent.click(await screen.findByRole('button', { name: 'payment-service process-payment INTERNAL OK' }));
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(screen.getByText('Refresh')).toBeEnabled());
    expect(within(panel()).getByText(internal.span_id)).toBeInTheDocument();
    data = { ...detail, spans: [root] };
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(within(panel()).getByText(root.span_id)).toBeInTheDocument());
  });
  it('keeps minimum-width bars bounded at the far edge with zero duration', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...detail,
      trace: { ...detail.trace, duration_us: 0 }, spans: [{ ...root, duration_us: 0, start_offset_us: 1 }] })));
    render(<TraceDetail traceId={id} />);
    await screen.findByRole('complementary');
    const bar = document.querySelector('.bar') as HTMLElement;
    expect(bar.style.left).toContain('calc(100% - 3px)');
    expect(bar.style.width).toContain('max(3px');
    expect(within(panel()).queryByText('Percent of trace')).not.toBeInTheDocument();
  });
  it.each([404, 422])('handles not-found status %i', async status => {
    vi.stubGlobal('fetch', vi.fn(async () => response({}, status)));
    render(<TraceDetail traceId={id} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Trace not found.');
  });
  it('handles empty spans safely', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({ ...detail, spans: [] })));
    render(<TraceDetail traceId={id} />);
    expect(await screen.findByText('No span data is available.')).toBeInTheDocument();
  });
  it('handles backend failure and offers Retry', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({}, 503)));
    render(<TraceDetail traceId={id} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('backend returned an error');
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });
  it('back link preserves list URL and root redirects to traces', async () => {
    window.history.replaceState(null, '', '/traces/' + id + '?returnTo=' + encodeURIComponent('/traces?status=ERROR&offset=50'));
    const rendered = render(<App />);
    expect(screen.getByText('← Back to traces')).toHaveAttribute('href', '/traces?status=ERROR&offset=50');
    rendered.unmount();
    vi.stubGlobal('fetch', vi.fn(async (url: string) => response(url.includes('/services') ? { services: [] } : { items: [], limit: 50, offset: 0 })));
    window.history.replaceState(null, '', '/'); render(<App />);
    expect(window.location.pathname).toBe('/traces');
    expect(await screen.findByText('No traces yet.')).toBeInTheDocument();
  });
});
