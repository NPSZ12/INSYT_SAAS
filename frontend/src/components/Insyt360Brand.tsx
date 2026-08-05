type Insyt360BrandProps = {
  className?: string;
  lightBackground?: boolean;
};

export default function Insyt360Brand({
  className = "",
  lightBackground = false,
}: Insyt360BrandProps) {
  const primaryText = lightBackground
    ? "text-sky-700"
    : "text-white";

  return (
    <span
      className={`insyt-brand inline-flex items-end gap-0 whitespace-nowrap leading-none ${className}`}
      aria-label="INSYT360"
    >
      <span className={primaryText}>I</span>
      <span className="text-sky-400">N</span>
      <span className={primaryText}>SYT</span>

      <span className="insyt-brand mb-[0.07em] text-[0.75em] font-bold leading-none text-sky-400">
        360
      </span>
    </span>
  );
}