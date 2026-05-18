import type { CampaignResponse } from '../../types/twin';

export function SimulationCampaignMatrix({ campaign }: { campaign: CampaignResponse | null }) {
  return (
    <div className="mission-lab-card">
      <div className="mission-lab-card-head">
        <span>Simulation Campaign</span>
        <strong>{campaign ? `${campaign.run_count} runs` : 'waiting'}</strong>
      </div>
      {!campaign ? (
        <p>Run a campaign to score each candidate repair across environment branches and deterministic seeds.</p>
      ) : (
        <>
          <div className="campaign-meta">
            <span>Assembly v{campaign.assembly_version}</span>
            <code>{campaign.assembly_digest ? campaign.assembly_digest.slice(0, 12) : '--'}</code>
            <strong>{campaign.gate_status}</strong>
          </div>
          <div className="campaign-matrix">
            {campaign.scores.map(score => (
              <div className={`campaign-row ${score.plan_id === campaign.best_plan_id ? 'best' : ''}`} key={score.plan_id}>
                <strong>{score.label || score.plan_id}</strong>
                <span>{score.verdict}</span>
                <span>Pass {(score.pass_rate * 100).toFixed(0)}%</span>
                <span>Worst {score.worst_risk_score.toFixed(1)}</span>
                <span>Temp {score.max_temp_c.toFixed(1)}C</span>
                <span>Batt {score.min_battery_voltage.toFixed(2)}V</span>
                <span>Loss {score.max_packet_loss.toFixed(2)}</span>
              </div>
            ))}
          </div>
          {campaign.gate_reason && <div className="gate-note">{campaign.gate_reason}</div>}
        </>
      )}
    </div>
  );
}
