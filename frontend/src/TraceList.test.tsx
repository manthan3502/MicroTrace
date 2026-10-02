import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import TraceList from './TraceList';
import { response, trace } from './test/fixtures';

function mock(items = [trace]) {
  const fetcher = vi.fn(async (url: string) => response(url.startsWith('/api/v1/services') ?
    { services: ['order-service', 'payment-service'] } : { items, limit: 50, offset: 0 }));
  vi.stubGlobal('fetch', fetcher);
  return fetcher;
}
beforeEach(() => window.history.replaceState(null, '', '/traces'));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
describe('Trace List', () => {
  it('shows loading', () => {
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    render(<TraceList />); expect(screen.getByRole('status')).toHaveTextContent('Loading traces');
  });
  it('renders API rows and independent incomplete badge', async () => {
    mock([{ ...trace, incomplete: true }]); render(<TraceList />);
    expect(await screen.findByRole('link', { name: 'POST /orders' })).toHaveAttribute('href', expect.stringContaining('/traces/' + trace.trace_id));
    expect(screen.getByText('◌ INCOMPLETE')).toBeInTheDocument();
    expect(screen.getByText('✓ OK')).toBeInTheDocument();
    expect(screen.getAllByRole('columnheader')).toHaveLength(7);
  });
  it('applies filters through URL, resets offset, and does not fetch each keystroke', async () => {
    const fetcher = mock(); render(<TraceList />);
    await screen.findByRole('link', { name: 'POST /orders' });
    const count = fetcher.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Service'), { target: { value: 'payment-service' } });
    fireEvent.change(screen.getByLabelText('Status'), { target: { value: 'ERROR' } });
    fireEvent.change(screen.getByLabelText('Min duration (ms)'), { target: { value: '500' } });
    expect(fetcher.mock.calls).toHaveLength(count);
    fireEvent.click(screen.getByText('Apply'));
    await waitFor(() => expect(fetcher.mock.calls.at(-1)?.[0]).toBe('/api/v1/traces?limit=50&service=payment-service&status=ERROR&min_duration_ms=500'));
    expect(window.location.search).toContain('status=ERROR');
    fireEvent.click(screen.getByText('Reset'));
    await waitFor(() => expect(window.location.search).toBe(''));
  });
  it('invalid duration shows inline error and sends no request', async () => {
    const fetcher = mock(); render(<TraceList />);
    await screen.findByRole('link', { name: 'POST /orders' });
    const count = fetcher.mock.calls.length;
    fireEvent.change(screen.getByLabelText('Min duration (ms)'), { target: { value: '-1' } });
    fireEvent.click(screen.getByText('Apply'));
    expect(screen.getByRole('alert')).toHaveTextContent('integer duration');
    expect(fetcher.mock.calls).toHaveLength(count);
  });
  it.each([
    ['/traces', 'No traces yet.'],
    ['/traces?status=ERROR', 'No traces match these filters.'],
    ['/traces?offset=50', 'No more traces.'],
  ])('renders empty state at %s', async (url, expected) => {
    window.history.replaceState(null, '', url); mock([]); render(<TraceList />);
    expect(await screen.findByText(expected)).toBeInTheDocument();
  });
  it('paginates and refresh preserves URL', async () => {
    const fetcher = mock(Array.from({ length: 50 }, (_, i) => ({ ...trace, trace_id: i.toString(16).padStart(32, '0') })));
    render(<TraceList />);
    await waitFor(() => expect(screen.getByText('Next')).toBeEnabled());
    fireEvent.click(screen.getByText('Next'));
    await waitFor(() => expect(fetcher.mock.calls.at(-1)?.[0]).toContain('offset=50'));
    expect(window.location.search).toBe('?offset=50');
    await waitFor(() => expect(screen.getByText('Refresh')).toBeEnabled());
    fireEvent.click(screen.getByText('Refresh'));
    await waitFor(() => expect(fetcher.mock.calls.at(-1)?.[0]).toContain('offset=50'));
  });
  it('shows network failure with Retry', async () => {
    vi.stubGlobal('fetch', vi.fn(() => Promise.reject(new TypeError('network'))));
    render(<TraceList />); expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach");
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });
  it('service metadata failure leaves other filters usable', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => response(url.includes('/services') ? {} : { items: [], limit: 50, offset: 0 }, url.includes('/services') ? 503 : 200)));
    render(<TraceList />); await screen.findByText('Services unavailable');
    expect(screen.getByLabelText('Service')).toBeDisabled();
    expect(screen.getByLabelText('Status')).toBeEnabled();
  });
  it('browser Back restores URL state', async () => {
    mock(); render(<TraceList />); await screen.findByRole('link', { name: 'POST /orders' });
    window.history.replaceState(null, '', '/traces?status=ERROR');
    fireEvent(window, new PopStateEvent('popstate'));
    expect(screen.getByLabelText('Status')).toHaveValue('ERROR');
  });
});
