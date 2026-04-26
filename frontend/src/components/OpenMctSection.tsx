export function OpenMctSection() {
  return (
    <section className="panel openmct-panel">
      <div className="panel-title">Open MCT Telemetry Page</div>
      <p>
        打开独立 Open MCT 页面查看同一组树莓派实时/历史遥测。它使用 <code>real/*</code> 命名空间，下一版会加入 <code>twin/*</code> 预测通道。
      </p>
      <a className="primary-link" href="/openmct.html" target="_blank" rel="noreferrer">Open MCT →</a>
    </section>
  );
}
