"use client";

import AzureProcessingCenterPanel from "./AzureProcessingCenterPanel";

type Props = {
  clientId: string;
  projectId: string;
  apiBase?: string;
};

export default function SummariesProcessingCenterPanel({
  clientId,
  projectId,
  apiBase = "",
}: Props) {
  return (
    <AzureProcessingCenterPanel
      workspace="summaries"
      clientId={clientId}
      projectId={projectId}
      apiBase={apiBase}
      title="INSYT Summaries Processing Center"
      subtitle="Upload source PDFs, run Summaries processing, prepare review-ready text, and build the foundation for PDF outline and summary-level batching."
    />
  );
}