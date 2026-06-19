"use client";

import { Suspense, useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import Input from "../../../components/Input";
import FormLabel from "../../../components/FormLabel";
import { apiGet } from "../../../lib/api";

type ProjectFile = {
  doc_id: string;
  coding?: string;
  file_name: string;
  extension: string;
  blob_path: string;
  size: string;
  last_modified: string;
};

function FilesPageContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const clientId = searchParams.get("client") || "";
  const projectId = searchParams.get("project") || "";

  const [files, setFiles] = useState<ProjectFile[]>([]);
  const [docIdSearch, setDocIdSearch] = useState("");
  const [codingSearch, setCodingSearch] = useState("");
  const [fileNameSearch, setFileNameSearch] = useState("");
  const [extensionSearch, setExtensionSearch] = useState("");
  const [metadataSearch, setMetadataSearch] = useState("");
  const [codingMap, setCodingMap] = useState<Record<string, string>>({});

  function openDocument(file: ProjectFile) {
    const storedUser =
      typeof window !== "undefined"
        ? localStorage.getItem("insyt_user")
        : null;

    const user = storedUser ? JSON.parse(storedUser) : null;
    const role = String(user?.role || "").toLowerCase();

    if (role === "1l" || role === "1lm") {
      return;
    }

    const docId =
      file.doc_id ||
      file.file_name?.replace(/\.[^/.]+$/, "") ||
      "";

    const nativeBlob =
      file.blob_path ||
      "";

    if (!docId) {
      console.error("Unable to open Capture file because doc_id is missing", file);
      return;
    }

    const params = new URLSearchParams();

    if (clientId) params.set("client", clientId);
    if (projectId) params.set("project", projectId);
    params.set("doc", docId);

    if (nativeBlob) {
      params.set("native_blob", nativeBlob);
    }

    router.push(`/capture/review/doc?${params.toString()}`);
  }

  useEffect(() => {
    if (!projectId) return;

    apiGet(
      `/api/capture/files?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(
        projectId
      )}&folder=${encodeURIComponent("source/native")}`
    )
      .then((response: any) => {
        console.log("FILES RESPONSE", response);

        const incomingFiles = Array.isArray(response)
          ? response
          : response?.files || [];

        setFiles(incomingFiles);
      })
      .catch(console.error);
  }, [clientId, projectId]);

  useEffect(() => {
    if (!projectId) return;

    apiGet(
      `/api/review/coding-map?client=${encodeURIComponent(
        clientId
      )}&project=${encodeURIComponent(projectId)}&workspace=capture`
    )
      .then((response: Record<string, string>) => {
        setCodingMap(response || {});
      })
      .catch(console.error);
  }, [clientId, projectId]);

  function getFileCoding(file: ProjectFile) {
    const docId = file.doc_id || "";
    const docIdWithoutExtension = docId.replace(/\.[^/.]+$/, "");

    return (
      codingMap[docId] ||
      codingMap[docIdWithoutExtension] ||
      file.coding ||
      ""
    );
  }

  const filteredFiles = useMemo(() => {
    return files.filter((file) => {
      const docIdMatch = file.doc_id
        .toLowerCase()
        .includes(docIdSearch.toLowerCase());

      const coding = getFileCoding(file);
      const codingMatch = coding
        .toLowerCase()
        .includes(codingSearch.toLowerCase());

      const fileNameMatch = file.file_name
        .toLowerCase()
        .includes(fileNameSearch.toLowerCase());

      const extensionMatch = file.extension
        .toLowerCase()
        .includes(extensionSearch.toLowerCase());

      const metadataText = [file.blob_path, file.size, file.last_modified]
        .join(" ")
        .toLowerCase();

      const metadataMatch = metadataText.includes(
        metadataSearch.toLowerCase()
      );

      return (
        docIdMatch &&
        codingMatch &&
        fileNameMatch &&
        extensionMatch &&
        metadataMatch
      );
    });
  }, [
    files,
    codingMap,
    docIdSearch,
    codingSearch,
    fileNameSearch,
    extensionSearch,
    metadataSearch,
  ]);

  if (!projectId) {
    return (
      <AppShell>
        <PageContainer>
          <PageHeader
            title="No Project Selected"
            subtitle="Return to Projects and select a project first."
          />
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Files"
          subtitle={`All project files for ${projectId.replaceAll("_", " ")}.`}
        />

        <ContentCard title="File Search">
          <div className="grid grid-cols-5 gap-4">
            <div>
              <FormLabel>Search Doc ID</FormLabel>
              <Input
                value={docIdSearch}
                onChange={setDocIdSearch}
                placeholder="Doc ID"
              />
            </div>

            <div>
              <FormLabel>Search Coding</FormLabel>
              <Input
                value={codingSearch}
                onChange={setCodingSearch}
                placeholder="Responsive"
              />
            </div>

            <div>
              <FormLabel>Search File Name</FormLabel>
              <Input
                value={fileNameSearch}
                onChange={setFileNameSearch}
                placeholder="File name"
              />
            </div>

            <div>
              <FormLabel>Search Extension</FormLabel>
              <Input
                value={extensionSearch}
                onChange={setExtensionSearch}
                placeholder="pdf, txt, xlsx"
              />
            </div>

            <div>
              <FormLabel>Search Metadata</FormLabel>
              <Input
                value={metadataSearch}
                onChange={setMetadataSearch}
                placeholder="path, size, modified"
              />
            </div>
          </div>
        </ContentCard>

        <div className="mt-6">
          <ContentCard title={`Project Files (${filteredFiles.length})`}>
            <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[70vh]">
              <table className="min-w-max w-full text-xs">
                <thead className="bg-slate-900 text-slate-400 sticky top-0 z-20">
                  <tr>
                    <th className="p-3 text-left">Doc ID</th>
                    <th className="p-3 text-left">Coding</th>
                    <th className="p-3 text-left">File Name</th>
                    <th className="p-3 text-left">Extension</th>
                    <th className="p-3 text-left">Blob Path</th>
                    <th className="p-3 text-left">Size</th>
                    <th className="p-3 text-left">Last Modified</th>
                  </tr>
                </thead>

                <tbody>
                  {filteredFiles.map((file) => (
                    <tr
                      key={file.blob_path}
                      className="border-t border-slate-800"
                    >
                      <td className="p-3">
                        <button
                          type="button"
                          onClick={() => openDocument(file)}
                          className="text-sky-400 hover:text-sky-300 underline"
                        >
                          {file.doc_id}
                        </button>
                      </td>

                      <td className="p-3 text-slate-300 whitespace-nowrap">
                        {getFileCoding(file)}
                      </td>

                      <td className="p-3 text-slate-300 whitespace-nowrap">
                        {file.file_name}
                      </td>

                      <td className="p-3 text-slate-300 whitespace-nowrap">
                        {file.extension}
                      </td>

                      <td className="p-3 text-slate-400 whitespace-nowrap">
                        {file.blob_path}
                      </td>

                      <td className="p-3 text-slate-300 whitespace-nowrap">
                        {file.size}
                      </td>

                      <td className="p-3 text-slate-300 whitespace-nowrap">
                        {file.last_modified}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </ContentCard>
        </div>
      </PageContainer>
    </AppShell>
  );
}

export default function FilesPage() {
  return (
    <Suspense fallback={<div>Loading files...</div>}>
      <FilesPageContent />
    </Suspense>
  );
}