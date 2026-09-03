type InputProps = {
  placeholder?: string;
  type?: string;
  value?: string;
  onChange?: (value: string) => void;
  onKeyDown?: React.KeyboardEventHandler<HTMLInputElement>;
  disabled?: boolean;
  className?: string;
};

export default function Input({
  placeholder,
  type = "text",
  value,
  onChange,
  onKeyDown,
  disabled = false,
  className = "",
}: InputProps) {
  return (
    <input
      type={type}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      placeholder={placeholder}
      onKeyDown={onKeyDown}
      disabled={disabled}
      className={`insyt-control insyt-input ${className}`}
    />
  );
}