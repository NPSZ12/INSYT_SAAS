"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import Input from "../../components/Input";
import TextArea from "../../components/TextArea";
import Select from "../../components/Select";
import FormLabel from "../../components/FormLabel";
import DataTable from "../../components/DataTable";
import { apiGet, apiPost } from "../../lib/api";
import { FolderOpen } from "lucide-react";

type SearchFolder = {
  folder_id: string;
  folder_name: string;
  search_type: string;
  search_terms: string[];
  hit_count: number;
  document_count: number;
};

type SearchHit = {
  folder_id: string;
  project_id: string;
  doc_id: string;
  file_name: string;
  blob_name: string;
  term: string;
  search_type: string;
  tag: string;
};

function SearchFoldersPageContent() {
  const searchParams = useSearchParams();
  const projectId = searchParams.get("project");

  const [folders, setFolders] = useState<SearchFolder[]>([]);
  const [folderName, setFolderName] = useState("");
  const [searchType, setSearchType] = useState("text");
  const [searchTerms, setSearchTerms] = useState("");
  const [message, setMessage] = useState("");

  const [selectedFolder, setSelectedFolder] = useState<SearchFolder | null>(null);
  const [hits, setHits] = useState<SearchHit[]>([]);

  function loadFolders() {
    if (!projectId) return;

    apiGet(`/api/search-folders?project=${projectId}`)
      .then(setFolders)
      .catch(console.error);
  }

  useEffect(() => {
    loadFolders();
  }, [projectId]);

  function openFolder(folder: SearchFolder) {
    setSelectedFolder(folder);

    apiGet(`/api/search-folders/${folder.folder_id}/hits`)
      .then(setHits)
      .catch(console.error);
  }

  function deleteFolder(folderId: string) {
    const confirmed = window.confirm(
      "Confirm Deletion: This will delete the search folder and its saved hits. Continue?"
    );

    if (!confirmed) {
      return;
    }

    apiPost(`/api/search-folders/${folderId}/delete`, {})
      .then(() => {
        setMessage("Search folder deleted.");
        setSelectedFolder(null);
        setHits([]);
        loadFolders();
      })
      .catch(() => setMessage("Delete failed."));
  }

  function createFolder() {
    if (!projectId) return;

    const terms = searchTerms
      .split("\n")
      .map((term) => term.trim())
      .filter(Boolean);

    apiPost("/api/search-folders/create", {
      project_id: projectId,
      folder_name: folderName,
      search_type: searchType,
      search_terms: terms,
    })
      .then((response) => {
        if (response.status === "duplicate_name") {
          setMessage(response.message);
          return;
        }

        setMessage(
          `Search folder created. Supplemental batch: ${response.batch_id}`
        );
        setFolderName("");
        setSearchTerms("");
        loadFolders();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Search folder creation failed. Check backend console.");
      });
  }

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

  const columns = [
    { key: "folder_id", label: "Folder ID" },
    { key: "folder_name", label: "Folder Name" },
    { key: "search_type", label: "Type" },
    { key: "document_count", label: "Documents" },
    { key: "hit_count", label: "Hits" },
  ];

  const tableRows = folders.map((folder) => ({
    folder_id: folder.folder_id,
    folder_name: folder.folder_name,
    search_type: folder.search_type,
    document_count: String(folder.document_count),
    hit_count: String(folder.hit_count),
  }));

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Search Folders"
          subtitle={`Create text or regex search folders for ${projectId.replaceAll("_", " ")}.`}
        />

        <div className="grid grid-cols-2 gap-6 mb-6">
          <ContentCard title="Create Search Folder">
            <FormLabel>Folder Name</FormLabel>
            <div className="mb-4">
              <Input
                value={folderName}
                onChange={setFolderName}
                placeholder="Example: SSN_Hits"
              />
            </div>

            <FormLabel>Search Type</FormLabel>
            <div className="mb-4">
              <Select value={searchType} onChange={setSearchType}>
                <option value="text">Text Search</option>
                <option value="regex">Regex Search</option>
                <option value="boolean">Boolean Search</option>
              </Select>
            </div>

            <FormLabel>Search Terms / Regex Patterns</FormLabel>
            <div className="mb-6">
              <TextArea
                rows={8}
                value={searchTerms}
                onChange={setSearchTerms}
                placeholder={"One term or regex per line"}
              />
            </div>

            <Button fullWidth onClick={createFolder}>
              Create Search Folder
            </Button>

            {message && (
              <p className="text-sm text-teal-400 mt-4">
                {message}
              </p>
            )}
          </ContentCard>

          <ContentCard title="Search Tips">
            {searchType === "text" && (
              <div className="space-y-3 text-slate-400 text-sm">
                <p>
                  <span className="text-white font-semibold">Text Search</span> is best for
                  simple words or phrases that should appear exactly in the extracted text.
                </p>

                <div className="bg-slate-950 border border-slate-800 rounded-xl p-4">
                  <p className="text-white mb-2">Examples:</p>
                  <p>Social Security</p>
                  <p>passport</p>
                  <p>employee ID</p>
                </div>

                <p>
                  Best for quick review sets, obvious terms, names, addresses, IDs, and
                  straightforward keyword searches.
                </p>
              </div>
            )}

            {searchType === "regex" && (
              <div className="space-y-3 text-slate-400 text-sm">
                <p>
                  <span className="text-white font-semibold">Regex Search</span> is best
                  for patterns like SSNs, dates, account numbers, or structured identifiers.
                </p>

                <div className="bg-slate-950 border border-slate-800 rounded-xl p-4">
                  <p className="text-white mb-2">Examples:</p>
                  <p>SSN1: <code>\\b\\d{3}-\\d{2}-\\d{4}\\b</code></p>
                  <p>SSN2: <code>{"[0-9]{3}-[0-9]{2}-[0-9]{4}"}</code></p>
                  <p>DOB1: <code>{"\\b\\d{1,2}/\\d{1,2}/\\d{2,4}\\b"}</code></p>
                  <p>DOB2: <code>{"[0-9]{1,2}-[0-9]{1,2}-[0-9]{4}"}</code></p>
                  <p>ZIP: <code>{"\\b\\d{5}(?:-\\d{4})?\\b"}</code></p>
                </div>

                <p>
                  Best for predictable formats. Use carefully because broad regex patterns
                  can create noisy hit sets.
                </p>
              </div>
            )}

            {searchType === "boolean" && (
              <div className="space-y-3 text-slate-400 text-sm">
                <p>
                  <span className="text-white font-semibold">Boolean Search</span> is best
                  for eDiscovery-style logic, proximity searches, and targeted concept sets.
                </p>

                <div className="bg-slate-950 border border-slate-800 rounded-xl p-4">
                  <p className="text-white mb-2">Examples:</p>
                  <p><code>Cyber w/3 Discovery</code></p>
                  <p><code>passport AND visa</code></p>
                  <p><code>employee NOT contractor</code></p>
                  <p><code>"social security number"</code></p>
                </div>

                <p>
                  Best for names, related concepts, proximity review, inclusion/exclusion
                  searches, and defensible supplemental review batches.
                </p>
              </div>
            )}
          </ContentCard>

          <ContentCard title="Workflow Result">
            <p className="text-slate-400 mb-4">
              INSYT will scan all project text files, tag matching document hits
              with the requested term, and create a supplemental batch from the
              unique matching documents.
            </p>

            <p className="text-slate-400">
              Supplemental batch format:
            </p>

            <div className="mt-3 bg-slate-950 border border-slate-800 rounded-xl p-4">
              [folder_name]_00001
            </div>
          </ContentCard>
        </div>

        <ContentCard title="Search Folders">
          {folders.length === 0 ? (
            <p className="text-slate-500">
              No search folders created yet.
            </p>
          ) : (
            <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th className="p-3 text-left">Folder ID</th>
                    <th className="p-3 text-left">Folder Name</th>
                    <th className="p-3 text-left">Type</th>
                    <th className="p-3 text-left">Documents</th>
                    <th className="p-3 text-left">Hits</th>
                    <th className="p-3 text-left">Action</th>
                  </tr>
                </thead>

                <tbody>
                  {folders.map((folder) => (
                    <tr
                      key={folder.folder_id}
                      className="border-t border-slate-800 hover:bg-slate-900"
                    >
                      <td className="p-3">
                        <button
                          type="button"
                          onClick={() => openFolder(folder)}
                          className="flex items-center gap-2 text-teal-400 hover:text-teal-300 underline"
                        >
                          <FolderOpen size={16} />
                          {folder.folder_id}
                        </button>
                      </td>

                      <td className="p-3 text-white">
                        {folder.folder_name}
                      </td>

                      <td className="p-3 text-slate-300">
                        {folder.search_type}
                      </td>

                      <td className="p-3 text-slate-300">
                        {folder.document_count}
                      </td>

                      <td className="p-3 text-slate-300">
                        {folder.hit_count}
                      </td>

                      <td className="p-3">
                        <button
                          type="button"
                          onClick={() => deleteFolder(folder.folder_id)}
                          className="text-xs px-3 py-1 rounded bg-red-700 hover:bg-red-600 text-white"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </ContentCard>

        {selectedFolder && (
          <div className="mt-6">
            <ContentCard title={`Hits: ${selectedFolder.folder_name}`}>
              {hits.length === 0 ? (
                <p className="text-slate-500">
                  No hits found for this folder.
                </p>
              ) : (
                <div className="bg-slate-950 border border-slate-800 rounded-xl overflow-auto max-h-[60vh]">
                  <table className="w-full text-xs">
                    <thead className="bg-slate-900 text-slate-400 sticky top-0 z-10">
                      <tr>
                        <th className="p-3 text-left">Doc ID</th>
                        <th className="p-3 text-left">File Name</th>
                        <th className="p-3 text-left">Matched Term</th>
                        <th className="p-3 text-left">Tag</th>
                      </tr>
                    </thead>

                    <tbody>
                      {hits.map((hit, index) => (
                        <tr
                          key={`${hit.doc_id}-${hit.term}-${index}`}
                          className="border-t border-slate-800"
                        >
                          <td className="p-3 text-teal-400">
                            {hit.doc_id}
                          </td>

                          <td className="p-3 text-slate-300">
                            {hit.file_name}
                          </td>

                          <td className="p-3 text-slate-300">
                            {hit.term}
                          </td>

                          <td className="p-3 text-slate-300">
                            {hit.tag}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </ContentCard>
          </div>
        )}    

      </PageContainer>
    </AppShell>
  );
}

export default function SearchFoldersPage() {
  return (
    <Suspense fallback={<div>Loading...</div>}>
      <SearchFoldersPageContent />
    </Suspense>
  );
}