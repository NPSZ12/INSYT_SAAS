type EmptyStateProps = {
  title: string;
  message: string;
  className?: string;
};

export default function EmptyState({
  title,
  message,
  className = "",
}: EmptyStateProps) {
  return (
    <div className={`insyt-empty-state ${className}`}>
      <h3 className="insyt-empty-state-title">
        {title}
      </h3>

      <p className="insyt-empty-state-message">
        {message}
      </p>
    </div>
  );
}