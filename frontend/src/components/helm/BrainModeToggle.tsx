import type { BrainMode } from '../../types/orchestrator';

export function BrainModeToggle({
  disabled,
  onChange,
  value
}: {
  disabled?: boolean;
  onChange: (mode: BrainMode) => void;
  value: BrainMode;
}) {
  return (
    <div className="orchestrator-toggle-row two">
      <button
        className={value === 'classic_python' ? 'selected' : ''}
        disabled={disabled}
        onClick={() => onChange('classic_python')}
        type="button"
      >
        Classic Python
      </button>
      <button
        className={value === 'gemma_helm' ? 'selected' : ''}
        disabled={disabled}
        onClick={() => onChange('gemma_helm')}
        type="button"
      >
        E4B Helm
      </button>
    </div>
  );
}
