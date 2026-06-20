type ButtonProps = {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger";
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
  const baseStyles =
    "px-5 py-3 rounded-xl font-semibold transition-all duration-150 active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-sky-400 focus:ring-offset-2 focus:ring-offset-slate-950";

  const styles =
    variant === "primary"
      ? "bg-sky-500 hover:bg-sky-400 active:bg-sky-700 text-white shadow-md shadow-sky-950/30"
      : variant === "danger"
        ? "bg-red-600 hover:bg-red-500 active:bg-red-700 text-white shadow-md shadow-red-950/30"
        : "border border-slate-700 bg-slate-900 hover:bg-slate-700 hover:border-sky-500 active:bg-sky-900 text-slate-200 hover:text-white";

  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`${fullWidth ? "w-full" : ""} ${baseStyles} ${styles}`}
    >
      {children}
    </button>
  );
}