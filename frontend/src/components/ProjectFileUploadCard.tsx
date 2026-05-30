"use client";

import { useEffect, useState } from "react";

import ContentCard from "./ContentCard";
import FormLabel from "./FormLabel";
import Select from "./Select";
import { apiGet } from "../lib/api";

type ProjectFileUploadCardProps = {
  projects: string[];
  selectedProject: string;
  setSelectedProject: (value: string) => void;
  setMessage: (value: string) => void;
};

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
};

const workspaceOptions = [
  { value: "capture", label: "INSYT Capture" },
  { value: "summaries", label: "INSYT Summaries" },
  { value: "discovery", label: "INSYT Discovery" },
  { value: "development", label: "INSYT Development" },
];

const clientFolderOptions = [
  { value: "source/native", label: "Native" },
];

const adminFolderOptions = [
  { value: "source/native", label: "Native" },
  { value: "source/text", label: "Text" },
  { value: "source/metadata", label: "Metadata" },
  { value: "source/protocol", label: "Protocol" },
  { value: "review/batches", label: "Review Batches" },
  { value: "review/qc", label: "QC" },
  { value: "reports", label: "Reports" },
  { value: "exports", label: "Exports" },
  { value: "archive", label: "Archive" },
];

export default function ProjectFileUploadCard({
  selectedProject,
  setSelectedProject,
  setMessage,
}: ProjectFileUploadCardProps) {
  const [user, setUser] = useState<StoredUser | null>(null);

  const [selectedWorkspace, setSelectedWorkspace] =
    useState("");
  const [clients, setClients] = useState<string[]>([]);
  const [selectedClient, setSelectedClient] =
    useState("");

  const [workspaceProjects, setWorkspaceProjects] =
    useState<string[]>([]);

  const [selectedFolder, setSelectedFolder] =
    useState("source/native");

  const [selectedFiles, setSelectedFiles] =
    useState<File[]>([]);
  const [uploading, setUploading] = useState(false);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  const normalizedRole =
    user?.role?.toLowerCase() || "";

  const canSeeAllFolders =
    normalizedRole.includes("admin") ||
    normalizedRole === "rm";

  const folderOptions = canSeeAllFolders
    ? adminFolderOptions
    : clientFolderOptions;

  useEffect(() => {
    if (!selectedWorkspace) {
      setClients([]);
      setSelectedClient("");
      setWorkspaceProjects([]);
      setSelectedProject("");
      return;
    }

    apiGet(`/api/${selectedWorkspace}/clients`)
      .then((response) => {
        setClients(response.clients || []);
      })
      .catch((error) => {
        console.error(error);
        setClients([]);
        setMessage("Failed to load clients.");
      });
  }, [selectedWorkspace, setSelectedProject, setMessage]);

  useEffect(() => {
    if (!selectedWorkspace || !selectedClient) {
      setWorkspaceProjects([]);
      setSelectedProject("");
      return;
    }

    apiGet(
      `/api/${selectedWorkspace}/clients/${encodeURIComponent(
        selectedClient
      )}/projects`
    )
      .then((response) => {
        setWorkspaceProjects(response.projects || []);
      })
      .catch((error) => {
        console.error(error);
        setWorkspaceProjects([]);
        setMessage("Failed to load projects.");
      });
  }, [
    selectedWorkspace,
    selectedClient,
    setSelectedProject,
    setMessage,
  ]);

  async function handleUpload() {
    try {
      if (uploading) return;

      if (!selectedWorkspace) {
        setMessage("Select a workspace before uploading files.");
        return;
      }

      if (!selectedClient) {
        setMessage("Select a client before uploading files.");
        return;
      }

      if (!selectedProject) {
        setMessage("Select a project before uploading files.");
        return;
      }

      if (!selectedFolder) {
        setMessage("Select a folder before uploading files.");
        return;
      }

      if (selectedFiles.length === 0) {
        setMessage("Select at least one file.");
        return;
      }

      setUploading(true);
      setMessage("Uploading files...");

      const formData = new FormData();

      formData.append("workspace", selectedWorkspace);
      formData.append("client", selectedClient);
      formData.append("project_id", selectedProject);
      formData.append("folder", selectedFolder);

      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      const apiBaseUrl =
        process.env.NEXT_PUBLIC_API_BASE_URL ||
        "https://api.insyt360.com";

      const token = localStorage.getItem("insyt_token");

      const response = await fetch(
        `${apiBaseUrl}/api/${selectedWorkspace}/files/upload`,
        {
          method: "POST",
          headers: token
            ? {
                Authorization: `Bearer ${token}`,
              }
            : undefined,
          body: formData,
        }
      );

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(errorText);
      }

      const result = await response.json();

      setMessage(
        `${
          result.count || selectedFiles.length
        } file(s) uploaded successfully to ${selectedClient}/${selectedProject}/${selectedFolder}.`
      );

      setSelectedFiles([]);
    } catch (error: any) {
      console.error("Upload failed:", error);

      setMessage(
        `Upload failed: ${error?.message || "Unknown error"}`
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mt-8">
      <ContentCard title="Upload Files to Project">
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
          <div>
            <FormLabel>Select Workspace</FormLabel>

            <Select
              value={selectedWorkspace}
              onChange={(value) => {
                setSelectedWorkspace(value);
                setSelectedClient("");
                setSelectedProject("");
                setSelectedFolder("source/native");
              }}
            >
              <option value="">Select workspace...</option>

              {workspaceOptions.map((workspace) => (
                <option
                  key={workspace.value}
                  value={workspace.value}
                >
                  {workspace.label}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <FormLabel>Select Client</FormLabel>

            <Select
              value={selectedClient}
              onChange={(value) => {
                setSelectedClient(value);
                setSelectedProject("");
              }}
            >
              <option value="">Select client...</option>

              {clients.map((client) => (
                <option key={client} value={client}>
                  {client.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <FormLabel>Select Project</FormLabel>

            <Select
              value={selectedProject}
              onChange={setSelectedProject}
            >
              <option value="">Select project...</option>

              {workspaceProjects.map((project) => (
                <option key={project} value={project}>
                  {project.replaceAll("_", " ")}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <FormLabel>Select Folder</FormLabel>

            <Select
              value={selectedFolder}
              onChange={setSelectedFolder}
            >
              {folderOptions.map((folder) => (
                <option
                  key={folder.value}
                  value={folder.value}
                >
                  {folder.label}
                </option>
              ))}
            </Select>
          </div>

          <div className="md:col-span-4">
            <FormLabel>Select Files</FormLabel>

            <input
              type="file"
              multiple
              className="
                block w-full rounded-xl border border-slate-700
                bg-slate-950 px-3 py-2 text-sm text-slate-300
                file:mr-4 file:rounded-xl file:border
                file:border-sky-400 file:bg-sky-500
                file:px-4 file:py-2 file:font-semibold
                file:text-white file:transition-all file:duration-200
                hover:file:bg-teal-500 hover:file:border-teal-400
                hover:file:shadow-lg hover:file:shadow-teal-500/20
                cursor-pointer
              "
              onChange={(event) => {
                const files = Array.from(
                  event.target.files || []
                );

                setSelectedFiles(files);

                if (files.length === 0) {
                  setMessage("No files selected.");
                  return;
                }

                setMessage(
                  `${files.length} file(s) selected for upload.`
                );
              }}
            />

            {selectedFiles.length > 0 && (
              <p className="mt-2 text-xs text-slate-400">
                Ready to upload: {selectedFiles.length} file(s)
              </p>
            )}
          </div>

          <div className="md:col-span-4">
            <button
              type="button"
              onClick={handleUpload}
              disabled={uploading}
              className={`
                relative z-50 inline-flex items-center justify-center
                rounded-xl border px-5 py-3 text-sm font-semibold
                text-white shadow-md transition-all duration-200
                ${
                  uploading
                    ? "cursor-not-allowed border-slate-600 bg-slate-700 text-slate-300"
                    : "cursor-pointer border-sky-400 bg-sky-500 shadow-sky-500/20 hover:bg-teal-500 hover:border-teal-400 hover:shadow-lg hover:shadow-teal-500/30 hover:scale-[1.02] active:scale-[0.98]"
                }
              `}
            >
              {uploading ? "Uploading..." : "Upload Files to Project"}
            </button>
          </div>
        </div>
      </ContentCard>
    </div>
  );
}