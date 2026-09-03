type PageHeaderProps = {
  title: string;
  subtitle: string;
  className?: string;
};

export default function PageHeader({
  title,
  subtitle,
  className = "",
}: PageHeaderProps) {
  return (
    <div className={`insyt-page-header ${className}`}>
      <h1 className="insyt-page-title">
        {title}
      </h1>

      <p className="insyt-page-subtitle">
        {subtitle}
      </p>
    </div>
  );
}