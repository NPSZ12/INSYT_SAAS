type ContentCardProps = {
  title?: string;
  children: React.ReactNode;
  className?: string;
};

export default function ContentCard({
  title,
  children,
  className = "",
}: ContentCardProps) {
  return (
    <div className={`insyt-panel p-6 ${className}`}>
      {title && (
        <h3 className="insyt-section-title mb-6 text-xl insyt-text-primary">
          {title}
        </h3>
      )}

      {children}
    </div>
  );
}