"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import { apiGet, apiPost } from "../../../lib/api";

type XlFile = {
  doc_id: string;
  file_name: string;
  extension: string;
  blob_path: string;
  size: string;
  last_modified: string;
  workspace: string;
  client: string;
  project: string;
  folder: string;
  status: string;
};

type PreviewResponse = {
  file_name: string;
  extension: string;
  preview_type: "table" | "text" | "pdf" | "unsupported";
  sheets?: string[];
  active_sheet?: string;
  columns?: string[];
  rows?: Record<string, string>[];
  text?: string;
  message?: string;
  row_count_previewed?: number;
  total_columns?: number;
};

function getWorkspace(pathname: string) {
  if (pathname.startsWith("/summaries")) return "summaries";
  if (pathname.startsWith("/discovery")) return "discovery";
  return "capture";
}

function CyberUtilityPageContent() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || getWorkspace(pathname);
  const selectedProject = searchParams.get("project") || "";
  const selectedClient = searchParams.get("client") || "";

  const [message, setMessage] = useState("");
  const [files, setFiles] = useState<XlFile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<string[]>([]);
  const [search, setSearch] = useState("");
  const [loadingFiles, setLoadingFiles] = useState(false);

  const [preview, setPreview] = useState<PreviewResponse | null>(null);
  const [previewBlobPath, setPreviewBlobPath] = useState("");
  const [selectedSheet, setSelectedSheet] = useState("");
  const [loadingPreview, setLoadingPreview] = useState(false);

  const filteredFiles = useMemo(() => {
    const value = search.trim().toLowerCase();

    if (!value) return files;

    return files.filter((file) =>
      [
        file.doc_id,
        file.file_name,
        file.extension,
        file.blob_path,
        file.status,
        file.last_modified,
      ]
        .join(" ")
        .toLowerCase()
        .includes(value)
    );
  }, [files, search]);

  function loadXlFiles() {
    if (!selectedProject) {
      setMessage("Select a project first.");
      return;
    }

    setLoadingFiles(true);
    setMessage("");
    setPreview(null);
    setPreviewBlobPath("");

    const params = new URLSearchParams({
      workspace,
      project: selectedProject,
      folder: "source/native",
    });

    if (selectedClient) {
      params.set("client", selectedClient);
    }

    apiGet(`/api/cyber-utility/xl-processing/files?${params.toString()}`)
      .then((response: XlFile[]) => {
        setFiles(response);
        setSelectedFiles([]);
        setMessage(`Found ${response.length} XL/CSV file(s).`);
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load XL/CSV files.");
      })
      .finally(() => {
        setLoadingFiles(false);
      });
  }

  function toggleFile(blobPath: string) {
    setSelectedFiles((current) =>
      current.includes(blobPath)
        ? current.filter((item) => item !== blobPath)
        : [...current, blobPath]
    );
  }

  function selectAllFiltered() {
    setSelectedFiles(filteredFiles.map((file) => file.blob_path));
  }

  function clearSelection() {
    setSelectedFiles([]);
  }

  function loadPreview(blobPath: string, sheetName = "") {
    setPreviewBlobPath(blobPath);
    setLoadingPreview(true);
    setMessage("");

    const params = new URLSearchParams({
      blob_path: blobPath,
      limit: "100",
    });

    if (sheetName) {
      params.set("sheet_name", sheetName);
    }

    apiGet(`/api/${workspace}/native-preview?${params.toString()}`)
      .then((response: PreviewResponse) => {
        setPreview(response);

        if (response.active_sheet) {
          setSelectedSheet(response.active_sheet);
        }
      })
      .catch((error) => {
        console.error(error);
        setPreview(null);
        setMessage("Failed to load native preview.");
      })
      .finally(() => {
        setLoadingPreview(false);
      });
  }

  function changeSheet(sheetName: string) {
    setSelectedSheet(sheetName);

    if (previewBlobPath) {
      loadPreview(previewBlobPath, sheetName);
    }
  }

  function runXlProcessing() {
    if (!selectedProject) {
      setMessage("Select a project first.");
      return;
    }

    if (selectedFiles.length === 0) {
      setMessage("Select at least one XL/CSV file first.");
      return;
    }

    apiPost("/api/cyber-utility/jobs", {
      workspace,
      client: selectedClient || null,
      project_id: selectedProject,
      tool_name: "XL Processing",
      input_path: "source/native",
      output_path: "source/spreadsheets/Output",
      options: {
        selected_files: selectedFiles,
        delimiter: ",",
        build_master: true,
        extract_headers: true,
      },
    })
      .then((response) => {
        setMessage(
          `XL Processing queued. Job ID: ${response.job_id}`
        );
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to queue XL Processing job.");
      });
  }

  useEffect(() => {
    if (selectedProject) {
      loadXlFiles();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedProject, selectedClient, workspace]);

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="XL Processing"
          subtitle="Preview, select, and process Excel and CSV files from Azure-hosted project source/native folders."
        />

        {message && (
          <p className="text-sm text-sky-400 mb-6">
            {message}
          </p>
        )}

        <ContentCard title="XL Processing">
          <div className="flex flex-col gap-4">
            <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
              <div>
                <p className="text-sm text-slate-400">
                  Source folder:
                </p>
                <p className="text-sm text-slate-200 font-semibold">
                  {selectedClient || "(no client)"} / {selectedProject || "(no project)"} / source / native
                </p>
              </div>

              <div className="flex flex-wrap gap-3">
                <button
                  type="button"
                  onClick={loadXlFiles}
                  className="bg-slate-700 hover:bg-slate-600 text-white rounded-xl px-4 py-3 font-semibold"
                >
                  Refresh
                </button>

                <button
                  type="button"
                  onClick={selectAllFiltered}
                  className="bg-slate-700 hover:bg-slate-600 text-white rounded-xl px-4 py-3 font-semibold"
                >
                  Select Filtered
                </button>

                <button
                  type="button"
                  onClick={clearSelection}
                  className="bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-xl px-4 py-3 font-semibold"
                >
                  Clear
                </button>

                <button
                  type="button"
                  onClick={runXlProcessing}
                  className="bg-lime-50 hover:bg-lime-100 text-slate-800 rounded-xl px-4 py-3 font-semibold"
                >
                  Run Processing
                </button>
              </div>
            </div>

            <input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search doc ID, file name, extension, path, status..."
              className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500"
            />

            <div className="rounded-xl border border-slate-800 overflow-hidden">
              <div className="max-h-[360px] overflow-auto">
                <table className="min-w-full border-collapse text-sm">
                  <thead className="sticky top-0 bg-slate-900 z-10">
                    <tr>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        Select
                      </th>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        Doc ID
                      </th>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        File Name
                      </th>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        Ext
                      </th>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        Size
                      </th>
                      <th className="border-b border-slate-800 px-3 py-2 text-left text-slate-300">
                        Action
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredFiles.map((file) => (
                      <tr key={file.blob_path} className="border-b border-slate-900">
                        <td className="px-3 py-2">
                          <input
                            type="checkbox"
                            checked={selectedFiles.includes(file.blob_path)}
                            onChange={() => toggleFile(file.blob_path)}
                          />
                        </td>
                        <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                          {file.doc_id}
                        </td>
                        <td className="px-3 py-2 text-slate-300 whitespace-nowrap">
                          {file.file_name}
                        </td>
                        <td className="px-3 py-2 text-sky-300 uppercase">
                          {file.extension}
                        </td>
                        <td className="px-3 py-2 text-slate-400 whitespace-nowrap">
                          {file.size}
                        </td>
                        <td className="px-3 py-2">
                          <button
                            type="button"
                            onClick={() => loadPreview(file.blob_path)}
                            className="rounded-lg bg-sky-600 hover:bg-sky-500 text-white px-3 py-2 text-xs font-semibold"
                          >
                            Preview
                          </button>
                        </td>
                      </tr>
                    ))}

                    {!loadingFiles && filteredFiles.length === 0 && (
                      <tr>
                        <td
                          colSpan={6}
                          className="px-4 py-6 text-center text-slate-500"
                        >
                          No XL/CSV files found.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            <p className="text-xs text-slate-500">
              Selected files: {selectedFiles.length}
            </p>
          </div>
        </ContentCard>

        {(preview || loadingPreview) && (
          <div className="mt-6">
            <ContentCard title="Native Spreadsheet Preview">
              {loadingPreview && (
                <div className="p-6 text-slate-400">
                  Loading preview...
                </div>
              )}

              {!loadingPreview && preview?.preview_type === "table" && (
                <div className="flex flex-col gap-4">
                  <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-3">
                    <div>
                      <p className="text-sm font-semibold text-white">
                        {preview.file_name}
                      </p>
                      <p className="text-xs text-slate-500">
                        Previewing {preview.row_count_previewed || 0} rows
                      </p>
                    </div>

                    {preview.sheets && preview.sheets.length > 0 && (
                      <select
                        value={selectedSheet}
                        onChange={(event) => changeSheet(event.target.value)}
                        className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200"
                      >
                        {preview.sheets.map((sheet) => (
                          <option key={sheet} value={sheet}>
                            {sheet}
                          </option>
                        ))}
                      </select>
                    )}
                  </div>

                  <div className="rounded-xl border border-slate-800 max-h-[520px] overflow-auto">
                    <table className="min-w-full border-collapse text-sm">
                      <thead className="sticky top-0 bg-slate-900 z-10">
                        <tr>
                          {(preview.columns || []).map((column) => (
                            <th
                              key={column}
                              className="border-b border-r border-slate-800 px-3 py-2 text-left text-xs text-slate-300 whitespace-nowrap"
                            >
                              {column}
                            </th>
                          ))}
                        </tr>
                      </thead>

                      <tbody>
                        {(preview.rows || []).map((row, rowIndex) => (
                          <tr
                            key={rowIndex}
                            className={
                              rowIndex % 2 === 0
                                ? "bg-slate-950"
                                : "bg-slate-900/60"
                            }
                          >
                            {(preview.columns || []).map((column) => (
                              <td
                                key={`${rowIndex}-${column}`}
                                className="border-b border-r border-slate-900 px-3 py-2 text-slate-300 whitespace-nowrap max-w-[360px] overflow-hidden text-ellipsis"
                                title={row[column] || ""}
                              >
                                {row[column] || ""}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!loadingPreview && preview?.preview_type === "text" && (
                <pre className="whitespace-pre-wrap text-sm leading-7 text-slate-300">
                  {preview.text || "No preview text available."}
                </pre>
              )}
            </ContentCard>
          </div>
        )}
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <CyberUtilityPageContent />
    </Suspense>
  );
}