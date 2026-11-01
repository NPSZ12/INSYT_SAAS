"use client";

import { useEffect, useMemo, useState } from "react";
import { apiGet } from "../../lib/api";

type Workspace = "capture" | "discovery";
type FileEntry = { doc_id?: string; file_name?: string; native_blob?: string; blob_path?: string };
type BatchNavigation = {
  batch_doc_ids?: string[];
  batch_doc_index?: number;
  batch_doc_count?: number;
  previous_doc_id?: string;
  next_doc_id?: string;
};
const normalize = (value: string) => String(value || "").trim().replace(/\.[^.]+$/, "").toLowerCase();

export function useWorkspaceReviewNavigation(args: {
  workspace: Workspace; client: string; project: string; batch: string;
  doc: string; reviewDocId?: string; reviewNav?: BatchNavigation;
  fixedDocIds?: string[];
}) {
  const {workspace, client, project, batch, doc, reviewDocId, reviewNav, fixedDocIds} = args;
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState(false);
  const fixedKey = fixedDocIds?.join(";") || "";
  useEffect(() => {
    if (batch || !project || !client || fixedKey) {
      setFiles([]);
      setLoadError(false);
      setLoading(false);
      return;
    }
    let active = true;
    setLoading(true);
    setLoadError(false);
    const params = new URLSearchParams({client, project, folder: "source/native"});
    apiGet(`/api/${workspace}/files?${params.toString()}`)
      .then((result: unknown) => {
        if (!active) return;
        const payload = result as {files?: FileEntry[]} | FileEntry[];
        const entries = Array.isArray(payload) ? payload : (payload?.files || []);
        setFiles(entries.filter((item) => Boolean(item.doc_id || item.file_name)));
      })
      .catch(() => { if (active) { setFiles([]); setLoadError(true); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [workspace, client, project, batch, fixedKey]);
  return useMemo(() => {
    const direct = !batch;
    const entries = direct
      ? fixedKey
        ? (fixedDocIds || []).map((id) => ({doc_id: id} as FileEntry))
        : files
      : (reviewNav?.batch_doc_ids || []).map((id) => ({doc_id: id} as FileEntry));
    const ids = entries.map((entry) => entry.doc_id || entry.file_name || "");
    const activeId = normalize(reviewDocId || doc);
    const actual = ids.findIndex((id) => normalize(id) === activeId);
    const metadataIndex = reviewNav?.batch_doc_index;
    const index = actual >= 0 ? actual : (!direct && Number.isInteger(metadataIndex) && metadataIndex! >= 0 && metadataIndex! < ids.length ? metadataIndex! : -1);
    const count = ids.length;
    const entryAt = (i: number) => i >= 0 && i < entries.length ? entries[i] : undefined;
    const target = (i: number) => {
      const entry = entryAt(i);
      if (!entry) return null;
      const id = entry.doc_id || entry.file_name || "";
      return id ? {docId: id, nativeBlob: entry.native_blob || entry.blob_path || ""} : null;
    };
    const canNavigate = count > 0 && index >= 0;
    return {
      isDirect: direct,
      loading: direct && loading,
      loadError: direct && loadError,
      index,
      count,
      label: canNavigate ? `Doc ${index + 1} of ${count}` : (loading ? "Loading documents..." : "Doc - of -"),
      isFirst: canNavigate && index === 0,
      isLast: canNavigate && index === count - 1,
      first: canNavigate && index > 0 ? target(0) : null,
      previous: canNavigate && index > 0 ? target(index - 1) : null,
      next: canNavigate && index < count - 1 ? target(index + 1) : null,
      last: canNavigate && index < count - 1 ? target(count - 1) : null,
    };
  }, [batch, fixedKey, fixedDocIds, files, reviewNav, reviewDocId, doc, loading, loadError]);
}
