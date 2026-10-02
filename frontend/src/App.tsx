import TraceDetail from './TraceDetail';
import TraceList from './TraceList';
export default function App() {
  const match = /^\/traces\/([^/]+)$/.exec(window.location.pathname);
  if (!match && window.location.pathname !== '/traces') window.history.replaceState(null, '', '/traces');
  return <><header className="topbar"><a href="/traces">MicroTrace</a></header>
    {match ? <TraceDetail traceId={match[1]} /> : <TraceList />}</>;
}
