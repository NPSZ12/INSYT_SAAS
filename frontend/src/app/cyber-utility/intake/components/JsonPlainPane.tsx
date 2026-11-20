"use client";

import SharedIntakeInventory, {
  type SharedIntakeFile,
} from "./SharedIntakeInventory";

export type JsonPlainDataset = {
  docId: string;
  label: string;
  recordCount: number;
  secondaryLabel?: string;
  classification?: string;
  entityTypes?: string[];
  headerSetId?: string;
  sourcePath?: string;
  sourceFormat?: string;
};

type JsonPlainPaneProps = {
  fileCount?: number;
  recordCount?: number;
  packageCount?: number;
  datasets?: JsonPlainDataset[];
  selectedDocIds?: Record<string, boolean>;
  creatingHeaderSet?: boolean;
  onToggleDocument?: (docId: string, selected: boolean) => void;
  onSelectAll?: (docIds: string[]) => void;
  onClearSelection?: () => void;
  onCreateHeaderSet?: () => void;
  onOpenDocument?: (docId: string) => void;
  onOpenDocId?: (docId: string) => void;
  hideRecordCount?: boolean;
  defaultExpanded?: boolean;
  paneId?: string;
  onOpenHeaderSet?: (headerSetId: string) => void;
};

export default function JsonPlainPane({
  datasets = [],
  selectedDocIds = {},
  creatingHeaderSet = false,
  onToggleDocument,
  onSelectAll,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
  onOpenDocId,
  hideRecordCount = false,
  defaultExpanded = false,
  paneId,
  onOpenHeaderSet,
}: JsonPlainPaneProps) {
  const files: SharedIntakeFile[] = datasets.map((doc) => ({
    docId: doc.docId,
    filename: doc.label,
    classification: doc.classification,
    entityTypes: doc.entityTypes || [],
    source: doc.label,
    worksheet: "",
    visibility: "",
    sourcePath: doc.sourcePath || "",
    headerSetId: doc.headerSetId || "",
    recordCount: doc.recordCount,
    selectable: !doc.headerSetId,
  }));

  return (
    <SharedIntakeInventory
      title="JSON — Plain"
      subtitle="Generic JSON arrays, objects, nested records, JSONL, and other structured JSON datasets."
      files={files}
      selectedDocIds={selectedDocIds}
      creatingHeaderSet={creatingHeaderSet}
      createLabel="Generate AI Suggestions"
      onToggleDocument={onToggleDocument}
      onSelectAllFiltered={onSelectAll}
      onClearSelection={onClearSelection}
      onCreateHeaderSet={onCreateHeaderSet}
      onOpenDocument={onOpenDocument}
      onOpenDocId={onOpenDocId}
      hideRecordCount={hideRecordCount}
      defaultExpanded={defaultExpanded}
      paneId={paneId}
      onOpenHeaderSet={onOpenHeaderSet}
    />
  );
}
