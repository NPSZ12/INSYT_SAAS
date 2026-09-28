"use client";

import { useEffect, useState } from "react";

import Button from "./Button";
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
  client_access?: string[];
  workspace_access?: string[];
};

const workspaceOptions = [
  { value: "capture", label: "INSYT Capture" },
  { value: "summaries", label: "INSYT Summaries" },
  { value: "discovery", label: "INSYT Discovery" },
  { value: "development", label: "INSYT Development" },
];

const clientFolderOptions = [
  {
    value: "source/processing_center/uploads",
    label: "Processing Center",
  },
];

const adminFolderOptions = [
  {
    value: "source/processing_center/uploads",
    label: "Processing Center",
  },
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
    useState("source/processing_center/uploads");

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

  const isClientUser =
    normalizedRole === "client";

  const isSingleClientRole =
    normalizedRole === "client" ||
    normalizedRole === "client admin";


  function getBoundClientName() {
    if (!isSingleClientRole) {
      return "";
    }

    const clientNames = new Set<string>();

    for (const value of user?.client_access || []) {
      const raw = String(value || "").trim();

      if (!raw || raw === "ALL") {
        continue;
      }

      const parts = raw.split("/");

      if (parts.length >= 2) {
        clientNames.add(
          parts.slice(1).join("/")
        );
      } else {
        clientNames.add(raw);
      }
    }

    return clientNames.size === 1
      ? Array.from(clientNames)[0]
      : "";
  }


  const canSeeAllFolders =
    normalizedRole.includes("admin") ||
    normalizedRole === "rm";

  const folderOptions = canSeeAllFolders
    ? adminFolderOptions
    : clientFolderOptions;

  useEffect(() => {
    if (isClientUser) {
      setSelectedFolder(
        "source/processing_center/uploads"
      );
    }
  }, [isClientUser]);

  useEffect(() => {
    if (!selectedWorkspace) {
      setClients([]);
      setSelectedClient("");
      setWorkspaceProjects([]);
      setSelectedProject("");
      return;
    }

    apiGet(
      `/api/${selectedWorkspace}/clients`
    )
      .then((response) => {
        const loadedClients: string[] =
          response.clients || [];

        if (!isSingleClientRole) {
          setClients(loadedClients);
          return;
        }

        const boundClient =
          getBoundClientName();

        if (!boundClient) {
          setClients([]);
          setSelectedClient("");
          setWorkspaceProjects([]);
          setSelectedProject("");

          setMessage(
            "Your account does not have a valid Client / DBA assignment."
          );

          return;
        }

        const authorizedClients =
          loadedClients.filter(
            (client) =>
              client === boundClient
          );

        setClients(
          authorizedClients
        );

        if (
          authorizedClients.includes(
            boundClient
          )
        ) {
          setSelectedClient(
            boundClient
          );
        } else {
          setSelectedClient("");
          setWorkspaceProjects([]);
          setSelectedProject("");
        }
      })
      .catch((error) => {
        console.error(error);
        setClients([]);
        setSelectedClient("");
        setWorkspaceProjects([]);
        setSelectedProject("");
        setMessage("Failed to load clients.");
      });
  }, [
    selectedWorkspace,
    user,
    setSelectedProject,
    setMessage,
  ]);

  useEffect(() => {
    if (
      !selectedWorkspace ||
      !selectedClient
    ) {
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
        setWorkspaceProjects(
          response.projects || []
        );
      })
      .catch((error) => {
        console.error(error);
        setWorkspaceProjects([]);
        setMessage(
          "Failed to load projects."
        );
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
        setMessage(
          "Select a workspace before uploading files."
        );
        return;
      }

      if (!selectedClient) {
        setMessage(
          "Select a client before uploading files."
        );
        return;
      }

      if (isSingleClientRole) {
        const boundClient =
          getBoundClientName();

        if (
          !boundClient ||
          selectedClient !== boundClient
        ) {
          setMessage(
            "You may only upload files to your assigned Client / DBA."
          );
          return;
        }
      }

      if (!selectedProject) {
        setMessage(
          "Select a project before uploading files."
        );
        return;
      }

      if (!selectedFolder) {
        setMessage(
          "Select a folder before uploading files."
        );
        return;
      }

      if (selectedFiles.length === 0) {
        setMessage(
          "Select at least one file."
        );
        return;
      }

      setUploading(true);
      setMessage("Uploading files...");

      const formData = new FormData();

      formData.append(
        "workspace",
        selectedWorkspace
      );

      formData.append(
        "client",
        selectedClient
      );

      formData.append(
        "project_id",
        selectedProject
      );

      formData.append(
        "folder",
        selectedFolder
      );

      selectedFiles.forEach((file) => {
        formData.append("files", file);
      });

      const apiBaseUrl =
        process.env.NEXT_PUBLIC_API_BASE_URL ||
        "https://api.insyt360.com";

      const token =
        localStorage.getItem("insyt_token");

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
        const errorText =
          await response.text();

        throw new Error(errorText);
      }

      const result =
        await response.json();

      setMessage(
        `${
          result.count ||
          selectedFiles.length
        } file(s) uploaded successfully to ${selectedClient}/${selectedProject}/${selectedFolder}. ${
          selectedFolder ===
          "source/processing_center/uploads"
            ? "INSYT Admin will start processing when ready."
            : ""
        }`
      );

      setSelectedFiles([]);
    } catch (error: any) {
      console.error(
        "Upload failed:",
        error
      );

      setMessage(
        `Upload failed: ${
          error?.message ||
          "Unknown error"
        }`
      );
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mt-8">
      <ContentCard title="Upload Files to Project">
        <div className="grid grid-cols-1 items-end gap-4 md:grid-cols-4">
          <div>
            <FormLabel>
              Select Workspace
            </FormLabel>

            <Select
              value={selectedWorkspace}
              onChange={(value) => {
                setSelectedWorkspace(value);
                setSelectedClient("");
                setSelectedProject("");
                setSelectedFolder(
                  "source/processing_center/uploads"
                );
              }}
            >
              <option value="">
                Select workspace...
              </option>

              {workspaceOptions.map(
                (workspace) => (
                  <option
                    key={workspace.value}
                    value={workspace.value}
                  >
                    {workspace.label}
                  </option>
                )
              )}
            </Select>
          </div>

          <div>
            <FormLabel>
              Select Client
            </FormLabel>

            <Select
              value={selectedClient}
              disabled={isSingleClientRole}
              onChange={(value) => {
                setSelectedClient(value);
                setSelectedProject("");
              }}
            >
              <option value="">
                Select client...
              </option>

              {clients.map((client) => (
                <option
                  key={client}
                  value={client}
                >
                  {client.replaceAll(
                    "_",
                    " "
                  )}
                </option>
              ))}
            </Select>
          </div>

          <div>
            <FormLabel>
              Select Project
            </FormLabel>

            <Select
              value={selectedProject}
              onChange={setSelectedProject}
            >
              <option value="">
                Select project...
              </option>

              {workspaceProjects.map(
                (project) => (
                  <option
                    key={project}
                    value={project}
                  >
                    {project.replaceAll(
                      "_",
                      " "
                    )}
                  </option>
                )
              )}
            </Select>
          </div>

          <div>
            <FormLabel>
              Select Folder
            </FormLabel>

            <Select
              value={selectedFolder}
              disabled={isClientUser}
              onChange={(value) => {
                if (isClientUser) return;

                setSelectedFolder(value);
              }}
            >
              {folderOptions.map(
                (folder) => (
                  <option
                    key={folder.value}
                    value={folder.value}
                  >
                    {folder.label}
                  </option>
                )
              )}
            </Select>

            {isClientUser ? (
              <div className="mt-2 text-xs insyt-text-muted">
                Client uploads are routed
                to the Processing Center.
                INSYT Admin will review and
                start processing when ready.
              </div>
            ) : null}
          </div>

          <div className="md:col-span-4">
            <FormLabel>
              Select Files
            </FormLabel>

            <input
              type="file"
              multiple
              className="insyt-control insyt-file-input"
              onChange={(event) => {
                const files = Array.from(
                  event.target.files || []
                );

                setSelectedFiles(files);

                if (files.length === 0) {
                  setMessage(
                    "No files selected."
                  );
                  return;
                }

                setMessage(
                  `${files.length} file(s) selected for upload.`
                );
              }}
            />

            {selectedFiles.length > 0 && (
              <p className="mt-2 text-xs insyt-text-muted">
                Ready to upload:{" "}
                {selectedFiles.length}{" "}
                file(s)
              </p>
            )}
          </div>

          <div className="md:col-span-4">
            <Button
              type="button"
              onClick={handleUpload}
              disabled={uploading}
            >
              {uploading
                ? "Uploading..."
                : "Upload Files to Project"}
            </Button>
          </div>
        </div>
      </ContentCard>
    </div>
  );
}