type ButtonProps = {
  children: React.ReactNode;
  variant?:
    | "primary"
    | "secondary"
    | "success"
    | "warning"
    | "danger"
    | "info"
    | "ghost";
  fullWidth?: boolean;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  disabled?: boolean;
  className?: string;
  unstyled?: boolean;
};

export default function Button({
  children,
  variant = "primary",
  fullWidth = false,
  onClick,
  type = "button",
  disabled = false,
  className = "",
  unstyled = false,
}: ButtonProps) {
  const styles = unstyled
    ? className
    : [
        "insyt-btn",
        `insyt-btn-${variant}`,
        fullWidth ? "insyt-btn-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ");

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={styles}
    >
      {children}
    </button>
  );
}