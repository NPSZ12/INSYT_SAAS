type StatusBadgeProps = {
  children: React.ReactNode;
  variant?:
    | "neutral"
    | "info"
    | "success"
    | "warning"
    | "danger";
};

export default function StatusBadge({
  children,
  variant = "neutral",
}: StatusBadgeProps) {
  const variantClass =
    variant === "info"
      ? "insyt-status-info"
      : variant === "success"
        ? "insyt-status-success"
        : variant === "warning"
          ? "insyt-status-warning"
          : variant === "danger"
            ? "insyt-status-danger"
            : "insyt-status-neutral";

  return (
    <span className={`insyt-status ${variantClass}`}>
      {children}
    </span>
  );
}