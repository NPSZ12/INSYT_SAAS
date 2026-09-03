type CheckboxProps = {
  label: string;
  defaultChecked?: boolean;
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  disabled?: boolean;
  className?: string;
};

export default function Checkbox({
  label,
  defaultChecked = false,
  checked,
  onChange,
  disabled = false,
  className = "",
}: CheckboxProps) {
  return (
    <label
      className={`flex items-center gap-3 text-sm insyt-text-secondary ${className}`}
    >
      <input
        type="checkbox"
        defaultChecked={
          checked === undefined
            ? defaultChecked
            : undefined
        }
        checked={checked}
        onChange={(event) =>
          onChange?.(event.target.checked)
        }
        disabled={disabled}
        className="insyt-check"
      />

      <span>{label}</span>
    </label>
  );
}