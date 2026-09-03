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

function getStatusVariant(status: string) {
  const normalized = status.trim().toLowerCase();

  if (
    normalized.includes("complete") ||
    normalized.includes("active") ||
    normalized.includes("approved")
  ) {
    return "success" as const;
  }

  if (
    normalized.includes("pending") ||
    normalized.includes("hold") ||
    normalized.includes("review")
  ) {
    return "warning" as const;
  }

  if (
    normalized.includes("fail") ||
    normalized.includes("error") ||
    normalized.includes("rejected")
  ) {
    return "danger" as const;
  }

  if (
    normalized.includes("ready") ||
    normalized.includes("processing")
  ) {
    return "info" as const;
  }

  return "neutral" as const;
}

export default function ProjectCard({
  name,
  client,
  status,
  docs,
  qc,
  onOpen,
}: ProjectCardProps) {
  return (
    <div className="insyt-project-card">
      <div className="insyt-project-card-header">
        <div>
          <h2 className="insyt-project-card-title">
            {name}
          </h2>

          <p className="insyt-project-card-client">
            {client}
          </p>
        </div>

        <StatusBadge variant={getStatusVariant(status)}>
          {status}
        </StatusBadge>
      </div>

      <div className="insyt-project-card-stats">
        <div className="insyt-project-card-stat">
          <p className="insyt-project-card-stat-label">
            Documents
          </p>

          <p className="insyt-project-card-stat-value">
            {docs}
          </p>
        </div>

        <div className="insyt-project-card-stat">
          <p className="insyt-project-card-stat-label">
            QC
          </p>

          <p className="insyt-project-card-stat-value">
            {qc}
          </p>
        </div>
      </div>

      <div className="insyt-project-card-action">
        <Button fullWidth onClick={onOpen}>
          Open Project
        </Button>
      </div>
    </div>
  );
}