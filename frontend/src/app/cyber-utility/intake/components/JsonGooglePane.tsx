"use client";

import { useRef, useState } from "react";
import SharedIntakeInventory, {
  type SharedIntakeFile,
} from "./SharedIntakeInventory";
import type {
  StructuredIntakeGroup,
} from "./StructuredIntakePaneShell";

type Props = {
  fileCount?: number;
  recordCount?: number;
  packageCount?: number;
  files?: SharedIntakeFile[];
  groups?: StructuredIntakeGroup[];
  onOpenDocument?: (docId: string) => void;
  onCreateHeaderSet?: (docIds: string[]) => Promise<void>;
  onOpenHeaderSet?: (headerSetId: string) => void;
};

export default function JsonGooglePane({
  files = [],
  groups = [],
  onOpenDocument,
  onCreateHeaderSet,
  onOpenHeaderSet,
}: Props) {
  const [selectedDocIds, setSelectedDocIds] =
    useState<Record<string, boolean>>({});
  const [creatingHeaderSet, setCreatingHeaderSet] = useState(false);
  const submissionInProgress = useRef(false);

  const readyIds = new Set(
    files.filter(
      (file) =>
        file.selectable !== false &&
        !file.assigned &&
        !file.headerSetId
    ).map((file) => file.docId)
  );

  async function createSelectedHeaderSet() {
    if (!onCreateHeaderSet || submissionInProgress.current) return;

    const ids = Object.keys(selectedDocIds).filter(
      (id) => selectedDocIds[id] && readyIds.has(id)
    );

    if (ids.length === 0) return;

    submissionInProgress.current = true;
    setCreatingHeaderSet(true);
    setSelectedDocIds({});

    try {
      await onCreateHeaderSet(ids);
    } finally {
      submissionInProgress.current = false;
      setCreatingHeaderSet(false);
    }
  }

  return (
    <SharedIntakeInventory
      title="JSON — Google"
      subtitle="Google Workspace and related structured exports preserved in their native logical groupings."
      files={files}
      sourceGroups={groups}
      groupLabel="Collections"
      selectedDocIds={selectedDocIds}
      creatingHeaderSet={creatingHeaderSet}
      onToggleDocument={(docId, selected) => {
        if (!readyIds.has(docId)) return;
        setSelectedDocIds((prev) => ({
          ...prev,
          [docId]: selected,
        }));
      }}
      onSelectAllFiltered={(ids) => {
        const filtered = new Set(ids);
        setSelectedDocIds((prev) => {
          const next = { ...prev };
          for (const id of readyIds) {
            if (filtered.has(id)) next[id] = true;
          }
          return next;
        });
      }}
      onClearSelection={() => setSelectedDocIds({})}
      onCreateHeaderSet={createSelectedHeaderSet}
      onOpenDocument={onOpenDocument}
      onOpenHeaderSet={onOpenHeaderSet}
    />
  );
}
