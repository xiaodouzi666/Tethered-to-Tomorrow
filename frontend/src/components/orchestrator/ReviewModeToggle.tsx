import type { ReviewMode } from '../../types/orchestrator';

const modes: Array<{ id: ReviewMode; label: string }> = [
  { id: 'manual', label: 'Manual' },
  { id: 'assisted', label: 'Assisted' },
  { id: 'auto', label: 'Auto' }
];

export function ReviewModeToggle({
  disabled,
  onChange,
  value
}: {
  disabled?: boolean;
  onChange: (mode: ReviewMode) => void;
  value: ReviewMode;
}) {
  return (
    <div className="orchestrator-toggle-row">
      {modes.map(mode => (
        <button
          className={mode.id === value ? 'selected' : ''}
          disabled={disabled}
          key={mode.id}
          onClick={() => onChange(mode.id)}
          type="button"
        >
          {mode.label}
        </button>
      ))}
    </div>
  );
}
