"use client";

import { useState } from "react";
import StructuredIntakePaneShell from "./StructuredIntakePaneShell";

export type SharedIntakeFile = {
  docId: string;
  filename: string;
  classification?: string;
  entityTypes?: string[];
  source?: string;
  worksheet?: string;
  visibility?: string;
  sourcePath?: string;
  headerSetId?: string;
  assigned?: boolean;
  processingSetId?: string;
  sourceJobId?: string;
  sourceDocumentCount?: number;
  aiEntityCount?: number;
  recordCount?: number;
  selectable?: boolean;
  sourceDetails?: { label: string; value: string | number }[];
  openable?: boolean;
};

type Props = {
  title: string;
  subtitle: string;
  sourceGroups?: {
    id: string;
    label: string;
    recordCount: number;
    secondaryLabel?: string;
  }[];
  groupLabel?: string;
  files: SharedIntakeFile[];
  selectedDocIds?: Record<string, boolean>;
  creatingHeaderSet?: boolean;
  createLabel?: string;
  onToggleDocument?: (docId: string, selected: boolean) => void;
  onSelectAllFiltered?: (docIds: string[]) => void;
  onClearSelection?: () => void;
  onCreateHeaderSet?: () => void;
  onOpenDocument?: (docId: string) => void;
  onOpenHeaderSet?: (headerSetId: string) => void;
};

export default function SharedIntakeInventory({
  title,
  subtitle,
  sourceGroups = [],
  groupLabel = "Groups",
  files,
  selectedDocIds = {},
  creatingHeaderSet = false,
  createLabel = "Create Header Set",
  onToggleDocument,
  onSelectAllFiltered,
  onClearSelection,
  onCreateHeaderSet,
  onOpenDocument,
  onOpenHeaderSet,
}: Props) {
  const [classification, setClassification] = useState("all");
  const [entityType, setEntityType] = useState("all");
  const [source, setSource] = useState("all");
  const [status, setStatus] = useState("all");
  const [search, setSearch] = useState("");

  const isAssigned = (file: SharedIntakeFile) =>
    Boolean(file.assigned || file.headerSetId);

  const normalize = (value?: string) =>
    String(value || "").trim().toUpperCase()
      .replace(/[_-]+/g, " ").replace(/\s+/g, " ");

  const entityOptions = Array.from(
    new Set(files.flatMap((file) => file.entityTypes || []))
  ).sort();

  const sourceOptions = Array.from(
    new Set(
      files.map((file) => file.source || file.filename)
        .filter(Boolean)
    )
  ).sort();

  const filtered = files.filter((file) => {
    const hit = normalize(file.classification) === "HIT";
    const assigned = isAssigned(file);

    if (classification === "hit" && !hit) return false;
    if (classification === "no_hit" && hit) return false;
    if (entityType !== "all" &&
        !(file.entityTypes || []).includes(entityType)) return false;
    if (source !== "all" &&
        (file.source || file.filename) !== source) return false;
    if (status === "ready" && assigned) return false;
    if (status === "assigned" && !assigned) return false;

    const searchable = [
      file.docId, file.filename, file.source,
      file.worksheet, file.sourcePath,
      file.processingSetId, file.sourceJobId,
      ...(file.sourceDetails || []).flatMap((detail) => [
        detail.label, String(detail.value),
      ]),
      file.headerSetId, file.classification,
      ...(file.entityTypes || []),
    ].filter(Boolean).join(" ").toLowerCase();

    return searchable.includes(search.trim().toLowerCase());
  });

  const ready = files.filter((file) => !isAssigned(file)).length;
  const assigned = files.length - ready;
  const selected = files.filter(
    (file) => Boolean(selectedDocIds[file.docId])
      && !isAssigned(file)
      && file.selectable !== false
  ).length;

  const selectableFiltered = filtered.filter(
    (file) => !isAssigned(file) && file.selectable !== false
  );

  const selectClass =
    "mt-1 w-full rounded-lg border border-slate-700 " +
    "bg-slate-950 px-3 py-2 text-sm text-slate-200";

  return (
    <StructuredIntakePaneShell
      title={title}
      subtitle={subtitle}
      fileCount={files.length}
    >
      <div className="space-y-4">
        <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
          <label className="text-xs text-slate-400">
            Classification
            <select className={selectClass} value={classification}
              onChange={(e) => setClassification(e.target.value)}>
              <option value="all">All Files</option>
              <option value="hit">HIT</option>
              <option value="no_hit">No Hit</option>
            </select>
          </label>

          <label className="text-xs text-slate-400">
            Detected Entity
            <select className={selectClass} value={entityType}
              onChange={(e) => setEntityType(e.target.value)}>
              <option value="all">All Entity Types</option>
              {entityOptions.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>

          <label className="text-xs text-slate-400">
            Source / Workbook
            <select className={selectClass} value={source}
              onChange={(e) => setSource(e.target.value)}>
              <option value="all">All Sources</option>
              {sourceOptions.map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          </label>

          <label className="text-xs text-slate-400">
            Status
            <select className={selectClass} value={status}
              onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All Statuses</option>
              <option value="ready">Ready</option>
              <option value="assigned">Assigned</option>
            </select>
          </label>

          <label className="text-xs text-slate-400">
            Search
            <input className={selectClass} value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Doc ID, filename, path..." />
          </label>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
          <span>Ready: {ready} | Assigned: {assigned} | Selected: {selected}</span>
          <span className="ml-auto">
            Showing {filtered.length} of {files.length}
          </span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button type="button" className="rounded-lg border border-slate-700 px-3 py-2 text-xs"
            disabled={!onSelectAllFiltered || selectableFiltered.length === 0}
            onClick={() => onSelectAllFiltered?.(
              selectableFiltered.map((file) => file.docId)
            )}>
            Select All Filtered
          </button>

          <button type="button" className="rounded-lg border border-slate-700 px-3 py-2 text-xs"
            disabled={!onClearSelection || selected === 0}
            onClick={onClearSelection}>
            Clear Selection
          </button>

          <button type="button"
            className="ml-auto rounded-lg bg-sky-600 px-4 py-2 text-xs font-semibold disabled:opacity-40"
            disabled={!onCreateHeaderSet || selected === 0 || creatingHeaderSet}
            onClick={onCreateHeaderSet}>
            {creatingHeaderSet ? "Creating..." : createLabel}
          </button>
        </div>

        <div className="overflow-x-auto rounded-xl border border-slate-800">
          <table className="min-w-[1250px] w-full text-left text-sm">
            <thead className="bg-slate-950 text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-3">Select</th>
                <th className="px-3 py-3">Doc ID</th>
                <th className="px-3 py-3">Classification</th>
                <th className="px-3 py-3">Source / Workbook</th>
                <th className="px-3 py-3">Worksheet</th>
                <th className="px-3 py-3">Visibility</th>
                <th className="px-3 py-3">Detected Types</th>
                <th className="px-3 py-3">Status</th>
                <th className="px-3 py-3">Source Path</th>
                <th className="px-3 py-3">Records</th>
                <th className="px-3 py-3">Header Set / Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {filtered.map((file) => (
                <tr key={file.docId} className="hover:bg-slate-900/70">
                  <td className="px-3 py-3">
                    <input type="checkbox"
                      disabled={isAssigned(file) ||
                        file.selectable === false || !onToggleDocument}
                      checked={Boolean(selectedDocIds[file.docId])}
                      onChange={(e) =>
                        onToggleDocument?.(file.docId, e.target.checked)
                      } />
                  </td>
                  <td className="px-3 py-3 font-mono text-xs">
                    {onOpenDocument && file.openable !== false ? (
                      <button type="button" className="text-sky-400 underline"
                        onClick={() => onOpenDocument(file.docId)}>
                        {file.docId}
                      </button>
                    ) : file.docId}
                  </td>
                  <td className="px-3 py-3">
                    {normalize(file.classification) || "-"}
                  </td>
                  <td className="px-3 py-3">
                    <div>{file.source || file.filename}</div>
                    {(file.sourceDetails || []).map((detail) => (
                      <div key={detail.label}
                        className="mt-1 text-xs text-slate-500">
                        {detail.label}: {detail.value}
                      </div>
                    ))}
                  </td>
                  <td className="px-3 py-3">{file.worksheet || "-"}</td>
                  <td className="px-3 py-3">{file.visibility || "-"}</td>
                  <td className="px-3 py-3">
                    {(file.entityTypes || []).join(", ") || "-"}
                  </td>
                  <td className="px-3 py-3">
                    {isAssigned(file) ? "Assigned" : "Ready"}
                  </td>
                  <td className="max-w-[300px] truncate px-3 py-3 font-mono text-xs"
                    title={file.sourcePath || ""}>
                    {file.sourcePath || "-"}
                  </td>
                  <td className="px-3 py-3 text-right">
                    {file.recordCount ?? "-"}
                  </td>
                  <td className="px-3 py-3">
                    {file.headerSetId && onOpenHeaderSet ? (
                      <button type="button" className="text-sky-400 underline"
                        onClick={() => onOpenHeaderSet(file.headerSetId!)}>
                        {file.headerSetId}
                      </button>
                    ) : file.headerSetId || "-"}
                    {onOpenDocument && file.openable !== false && (
                      <button type="button"
                        className="ml-3 text-sky-400 underline"
                        onClick={() => onOpenDocument(file.docId)}>
                        Open
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={11}
                    className="px-4 py-10 text-center text-slate-400">
                    No files match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {sourceGroups.length > 0 && (
          <div className="rounded-xl border border-slate-800 p-4">
            <div className="mb-3 text-sm font-semibold text-slate-200">
              {groupLabel}
            </div>
            {sourceGroups.map((group) => (
              <div key={group.id}
                className="flex justify-between gap-3 border-t border-slate-800 py-2 text-xs">
                <div>
                  <div className="text-slate-200">{group.label}</div>
                  {group.secondaryLabel && (
                    <div className="text-slate-500">{group.secondaryLabel}</div>
                  )}
                </div>
                <div className="text-slate-400">
                  {group.recordCount} records
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </StructuredIntakePaneShell>
  );
}
