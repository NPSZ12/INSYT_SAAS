"use client";

import SharedIntakeInventory, {
  type SharedIntakeFile,
} from "./SharedIntakeInventory";

export type AIExtractionDataset = {
  docId: string;
  processingSetId: string;
  sourceJobId?: string;
  sourceDocumentCount: number;
  aiEntityCount: number;
  entityTypes?: string[];
  filename?: string;
  assigned?: boolean;
  headerSetId?: string;
};

type AIExtractionsPaneProps = {
  datasets?: AIExtractionDataset[];
  selectedDocIds?: Record<string, boolean>;
  creatingHeaderSet?: boolean;
  onToggleDocument?: (docId: string, selected: boolean) => void;
  onSelectAll?: (docIds: string[]) => void;
  onClearSelection?: () => void;
  onCreateHeaderSet?: () => void;
  onOpenDocument?: (docId: string) => void;
  onOpenHeaderSet?: (headerSetId: string) => void;
};

export default function AIExtractionsPane({
  datasets = [],
  selectedDocIds = {},
  creatingHeaderSet = false,
  onToggleDocument,
  onSelectAll,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
  onOpenHeaderSet,
}: AIExtractionsPaneProps) {
  const files: SharedIntakeFile[] = datasets.map((doc) => ({
    docId: doc.docId,
    filename: doc.filename || doc.processingSetId,
    source: doc.filename || doc.processingSetId,
    entityTypes: doc.entityTypes || [],
    recordCount: doc.aiEntityCount,
    assigned: Boolean(doc.assigned),
    headerSetId: doc.headerSetId || "",
    processingSetId: doc.processingSetId,
    sourceJobId: doc.sourceJobId,
    sourceDocumentCount: doc.sourceDocumentCount,
    aiEntityCount: doc.aiEntityCount,
    selectable: !doc.assigned,
    sourceDetails: [
      { label: "Processing Set", value: doc.processingSetId },
      { label: "Source Job", value: doc.sourceJobId || "-" },
      { label: "Source Docs", value: doc.sourceDocumentCount },
      { label: "AI Entities", value: doc.aiEntityCount },
    ],
  }));

  return (
    <SharedIntakeInventory
      title="AI-Extractions"
      subtitle="AI-grouped entities generated from existing Processing Sets and Data Element Detection results."
      files={files}
      selectedDocIds={selectedDocIds}
      creatingHeaderSet={creatingHeaderSet}
      onToggleDocument={onToggleDocument}
      onSelectAllFiltered={onSelectAll}
      onClearSelection={onClearSelection}
      onCreateHeaderSet={onCreateHeaderSet}
      onOpenDocument={onOpenDocument}
      onOpenHeaderSet={onOpenHeaderSet}
    />
  );
}
