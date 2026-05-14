type PageHeaderProps = {
  title: string;
  subtitle: string;
};

export default function PageHeader({ title, subtitle }: PageHeaderProps) {
  return (
    <div className="mb-10">
      <h1 className="text-4xl font-bold text-white">
        {title}
      </h1>

      <p className="text-slate-400 mt-2">
        {subtitle}
      </p>
    </div>
  );
}