export function OpenMctSection() {
  return (
    <section className="panel openmct-panel">
      <div className="panel-title">Open MCT Telemetry Page</div>
      <p>
        Open the connected Open MCT workspace for mission telemetry and Twin forecast review.
        The object tree now exposes <code>real/*</code> for live and historical Probe data and <code>twin/*</code> for prediction channels generated from the current Twin run.
      </p>
      <a className="primary-link" href="/openmct.html" target="_blank" rel="noreferrer">Open MCT →</a>
    </section>
  );
}
