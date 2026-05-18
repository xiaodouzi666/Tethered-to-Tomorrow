import type { EnvironmentEvent } from '../../types/twin';

interface TwinEnvironmentTimelineProps {
  events?: EnvironmentEvent[];
}

export function TwinEnvironmentTimeline({ events = [] }: TwinEnvironmentTimelineProps) {
  const visibleEvents = events.length ? events : [{
    t: 0,
    event_type: 'baseline_environment',
    label: 'No environment events above display threshold',
    payload: {}
  }];

  return (
    <div className="twin-environment-timeline">
      <div className="twin-section-title">Environment Timeline</div>
      <div className="twin-env-event-list">
        {visibleEvents.slice(0, 5).map((event, index) => (
          <div className="twin-env-event" key={`${event.event_type}-${index}`}>
            <span>{Math.round(event.t)}s</span>
            <strong>{event.label}</strong>
            <small>{event.event_type}</small>
          </div>
        ))}
      </div>
    </div>
  );
}
