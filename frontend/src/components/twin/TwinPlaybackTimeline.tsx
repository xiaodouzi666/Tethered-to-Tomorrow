import type { ChangeEvent, KeyboardEvent, PointerEvent } from 'react';
import { Pause, Play, SkipBack, SkipForward } from 'lucide-react';
import type { PlanPlaybackBundle, TwinPlaybackFrame } from '../../types/twin';

interface TwinPlaybackTimelineProps {
  bundle?: PlanPlaybackBundle | null;
  currentFrame?: TwinPlaybackFrame | null;
  index: number;
  isPlaying: boolean;
  onPlayChange: (playing: boolean) => void;
  onSeek: (index: number) => void;
  onStep: (direction: -1 | 1) => void;
}

export function TwinPlaybackTimeline({
  bundle,
  currentFrame,
  index,
  isPlaying,
  onPlayChange,
  onSeek,
  onStep
}: TwinPlaybackTimelineProps) {
  const frames = bundle?.frames ?? [];
  const last = Math.max(0, frames.length - 1);
  const t = currentFrame?.t ?? 0;
  const duration = frames[last]?.t ?? 0;
  const disabled = frames.length === 0;
  const riskPoints = frames.map((frame, frameIndex) => ({
    index: frameIndex,
    risk: frame.constraint_frame.risk_score,
    fail: frame.constraint_frame.verdict === 'FAIL'
  }));
  const seekToValue = (event: ChangeEvent<HTMLInputElement>) => {
    onSeek(Number(event.target.value));
  };
  const seekFromPointer = (event: PointerEvent<HTMLInputElement>) => {
    if (disabled || last <= 0) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (event.clientX - rect.left) / rect.width));
    onSeek(Math.round(ratio * last));
  };
  const seekFromKeyboard = (event: KeyboardEvent<HTMLInputElement>) => {
    if (disabled) return;
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      onSeek(Math.max(0, index - 1));
    } else if (event.key === 'ArrowRight') {
      event.preventDefault();
      onSeek(Math.min(last, index + 1));
    } else if (event.key === 'Home') {
      event.preventDefault();
      onSeek(0);
    } else if (event.key === 'End') {
      event.preventDefault();
      onSeek(last);
    }
  };

  return (
    <div className="twin-playback-panel">
      <div className="twin-playback-head">
        <div>
          <div className="twin-section-title">Playback Timeline</div>
          <strong>{bundle ? `${bundle.label} · ${bundle.verdict} risk ${bundle.risk_score.toFixed(1)}` : 'No playback loaded'}</strong>
        </div>
        <span>{Math.round(t)}s / {Math.round(duration)}s</span>
      </div>

      <div className="twin-playback-controls">
        <button disabled={disabled || index <= 0} onClick={() => onStep(-1)} type="button">
          <SkipBack size={14} /> Step
        </button>
        <button disabled={disabled} onClick={() => onPlayChange(!isPlaying)} type="button">
          {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          {isPlaying ? 'Pause' : 'Play'}
        </button>
        <button disabled={disabled || index >= last} onClick={() => onStep(1)} type="button">
          <SkipForward size={14} /> Step
        </button>
      </div>

      <div className="twin-timeline-track">
        <input
          aria-label="Twin playback frame"
          disabled={disabled}
          max={last}
          min={0}
          onChange={seekToValue}
          onKeyDown={seekFromKeyboard}
          onPointerDown={seekFromPointer}
          type="range"
          value={Math.min(index, last)}
        />
        <div className="twin-marker-row action">
          {(bundle?.action_events ?? []).map((event) => (
            <button
              key={`${event.step_index}-${event.action}`}
              onClick={() => onSeek(frameIndexForTime(frames, event.t))}
              style={{ left: `${percent(event.t, duration)}%` }}
              title={event.summary}
              type="button"
            >
              {event.action}
            </button>
          ))}
        </div>
        <div className="twin-marker-row risk">
          {riskPoints.filter((point) => point.fail || point.risk > 35).slice(0, 24).map((point) => (
            <i
              className={point.fail ? 'fail' : 'warn'}
              key={point.index}
              style={{ left: `${last ? (point.index / last) * 100 : 0}%` }}
              title={`risk ${point.risk.toFixed(1)}`}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function percent(t: number, duration: number): number {
  if (!duration) return 0;
  return Math.max(0, Math.min(100, (t / duration) * 100));
}

function frameIndexForTime(frames: TwinPlaybackFrame[], t: number): number {
  if (!frames.length) return 0;
  let bestIndex = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  frames.forEach((frame, index) => {
    const distance = Math.abs(frame.t - t);
    if (distance < bestDistance) {
      bestDistance = distance;
      bestIndex = index;
    }
  });
  return bestIndex;
}
