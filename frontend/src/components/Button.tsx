type ButtonProps = {
  children: React.ReactNode;
  variant?: "primary" | "secondary" | "danger";
  fullWidth?: boolean;
  onClick?: () => void;
  type?: "button" | "submit";
};

export default function Button({
  children,
  variant = "primary",
  fullWidth = false,
  onClick,
  type = "button",
}: ButtonProps) {
  const styles =
    variant === "primary"
      ? "bg-teal-500 hover:bg-sky-500 text-slate-700"
      : variant === "danger"
      ? "bg-red-600 hover:bg-red-500 text-white"
      : "border border-slate-700 hover:bg-slate-800 text-slate-200";

  return (
    <button
      type={type}
      onClick={onClick}
      className={`${fullWidth ? "w-full" : ""} px-5 py-3 rounded-xl font-semibold transition ${styles}`}
    >
      {children}
    </button>
  );
}








