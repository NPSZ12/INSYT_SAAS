type TextAreaProps = {
  placeholder?: string;
  rows?: number;
  value?: string;
  onChange?: (value: string) => void;
  disabled?: boolean;
  className?: string;
};

export default function TextArea({
  placeholder,
  rows = 4,
  value,
  onChange,
  disabled = false,
  className = "",
}: TextAreaProps) {
  return (
    <textarea
      rows={rows}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      placeholder={placeholder}
      disabled={disabled}
      className={`insyt-control insyt-textarea ${className}`}
    />
  );
}