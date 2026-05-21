import Button from "./Button";
import StatusBadge from "./StatusBadge";


type ProjectCardProps = {
  name: string;
  client: string;
  status: string;
  docs: string;
  qc: string;
  onOpen?: () => void;
};

export default function ProjectCard({
  name,
  client,
  status,
  docs,
  qc,
  onOpen,
}: ProjectCardProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 hover:border-sky-500 transition">
      <div className="flex justify-between items-start mb-6">
        <div>
          <h2 className="text-2xl font-semibold">{name}</h2>
          <p className="text-slate-400 mt-1">{client}</p>
        </div>

        <StatusBadge>{status}</StatusBadge>
      </div>

      <div className="grid grid-cols-2 gap-4 text-sm">
        <div className="bg-slate-950 rounded-xl p-4">
          <p className="text-slate-500">Documents</p>
          <p className="text-xl font-bold mt-1">{docs}</p>
        </div>

        <div className="bg-slate-950 rounded-xl p-4">
          <p className="text-slate-500">QC</p>
          <p className="text-xl font-bold mt-1">{qc}</p>
        </div>
      </div>

      <div className="mt-6">
        <Button fullWidth onClick={onOpen}>
          Open Project
        </Button>
      </div>
    </div>
  );
}








