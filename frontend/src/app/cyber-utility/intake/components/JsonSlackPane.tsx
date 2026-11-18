"use client";

import SharedIntakeInventory, {
  type SharedIntakeFile,
} from "./SharedIntakeInventory";
import type {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";

export type JsonSlackDataset = {
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

type JsonSlackPaneProps = {
  fileCount?: number;
  recordCount?: number;
  packageCount?: number;
  datasets?: JsonSlackDataset[];
  channels?: StructuredIntakeGroup[];
  selectedDocIds?: Record<string, boolean>;
  creatingHeaderSet?: boolean;
  onToggleDocument?: (docId: string, selected: boolean) => void;
  onSelectAll?: (docIds: string[]) => void;
  onClearSelection?: () => void;
  onCreateHeaderSet?: () => void;
  onOpenDocument?: (docId: string) => void;
  onOpenHeaderSet?: (headerSetId: string) => void;
};

export default function JsonSlackPane({
  datasets = [],
  channels = [],
  selectedDocIds = {},
  creatingHeaderSet = false,
  onToggleDocument,
  onSelectAll,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
  onOpenHeaderSet,
}: JsonSlackPaneProps) {
  const files: SharedIntakeFile[] = datasets.map((doc) => ({
    docId: doc.docId,
    filename: doc.label,
    classification: doc.classification,
    entityTypes: doc.entityTypes || [],
    source: doc.label,
    sourcePath: doc.sourcePath || "",
    headerSetId: doc.headerSetId || "",
    recordCount: doc.recordCount,
    selectable: !doc.headerSetId,
    sourceDetails: [
      ...(doc.secondaryLabel
        ? [{ label: "Package", value: doc.secondaryLabel }]
        : []),
      ...(channels.length
        ? [{ label: "Channels", value: channels.length }]
        : []),
    ],
  }));

  return (
    <SharedIntakeInventory
      title="JSON ? Slack"
      subtitle="Slack exports preserved by workspace, channel, thread, message, user, and source relationship."
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
