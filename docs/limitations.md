# Limitations

- Educational, portfolio-scale implementation; no production-scale guarantee.
- W3C Trace Context-aware version-00 subset. No tracestate processing, sampling,
  OTLP/gRPC or OpenTelemetry SDK/interoperability guarantee.
- Bounded, non-durable, best-effort export can lose spans during queue saturation,
  delivery failure or shutdown. No retries/backoff infrastructure.
- Incomplete identifies structural gaps: missing parents/root, multiple roots and
  cycles. It cannot detect every dropped child or prove delivery completeness.
- UTC clocks may differ across hosts; local duration remains monotonic. Visual
  scale can extend past root duration; very short bars have a 3px minimum.
- Single-host Compose; named volumes survive container restarts, not VM/disk loss.
  No managed backup, replication, retention or automated recovery system.
- No app authentication/multitenancy. Deploy fake demo data only. Public Order
  accepts the three scenarios; production ingestion stays private.
- No metrics/logging platform, anomaly detection, live streaming or extra pages.
- HTTP suffices for the approved portfolio MVP. HTTPS requires an actual domain
  and certificate setup. Never send sensitive data to the public demo.
- Public demo uses the approved EC2 IP over HTTP; no domain/TLS or static-IP
  allocation was added. An address change requires updating the documented link.
