type FormLabelProps = {
  children: React.ReactNode;
  className?: string;
};

export default function FormLabel({
  children,
  className = "",
}: FormLabelProps) {
  return (
    <label className={`insyt-form-label ${className}`}>
      {children}
    </label>
  );
}