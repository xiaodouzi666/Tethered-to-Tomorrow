import { PauseCircle } from 'lucide-react';

export function TwinPlaceholder() {
  return (
    <section className="panel twin-panel">
      <div className="panel-title"><PauseCircle size={16}/> Digital Twin Panel（v1 占位）</div>
      <p>
        当前第一版按你的要求先完成电脑端前端与树莓派端飞船模拟器联调；完整数字孪生将在下一版接入。
      </p>
      <div className="twin-mock-chart">
        <div className="line real" />
        <div className="line twin" />
        <div className="threshold" />
        <span className="chart-label real-label">Real telemetry</span>
        <span className="chart-label twin-label">Twin predicted（reserved）</span>
        <span className="chart-label threshold-label">Constraint threshold</span>
      </div>
      <div className="constraint-list">
        <div><span className="pending"/> temp_c ≤ 85°C</div>
        <div><span className="pending"/> battery_voltage ≥ 10.5V</div>
        <div><span className="pending"/> packet_loss ≤ 0.60</div>
      </div>
      <button disabled>Run in Twin（v2）</button>
    </section>
  );
}
