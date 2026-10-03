"use client";

import {
  Suspense,
  useEffect,
  useMemo,
  useState,
} from "react";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import { apiGet, apiPost } from "../../lib/api";

type StoredUser = {
  username: string;
  display_name: string;
  role: string;
  status?: string;
};

type AccessUser = {
  username: string;
  display_name: string;
  email?: string;
  role: string;
  status: string;
  workspace_access?: string[];
  client_access?: string[];
  project_access?: string[];
  permissions?: string[];
  auth_provider?: string;
  staffing_groups?: string[];
  performance_score?: number | null;
  performance_band?: string;
};

type ProjectRow = {
  workspace: string;
  workspaceLabel: string;
  client: string;
  project: string;
  projectKey: string;
};

type BulkResponse = {
  status: string;
  project_id: string;
  assigned?: string[];
  removed?: string[];
  unchanged?: string[];
  not_found?: string[];
  assigned_count?: number;
  removed_count?: number;
  unchanged_count?: number;
  not_found_count?: number;
};

const workspaces = [
  {
    value: "capture",
    label: "INSYT Capture",
  },
  {
    value: "discovery",
    label: "INSYT Discovery",
  },
  {
    value: "summaries",
    label: "INSYT Summaries",
  },
];

function makeProjectKey(
  workspace: string,
  client: string,
  project: string
) {
  return `${workspace}/${client}/${project}`;
}

function prettyName(value: string) {
  return String(value || "").replaceAll("_", " ");
}

function normalizeRole(role: string) {
  const clean = String(role || "")
    .trim()
    .toLowerCase();

  if (
    clean === "rm" ||
    clean === "review manager"
  ) {
    return "RM";
  }

  if (clean === "insyt manager") {
    return "SRM";
  }

  if (
    clean === "1l" ||
    clean === "1l reviewer"
  ) {
    return "Reviewer";
  }

  if (clean === "admin") {
    return "Admin";
  }

  if (clean === "tl") {
    return "TL";
  }

  if (clean === "qc") {
    return "QC";
  }

  if (clean === "insyt admin") {
    return "INSYT Admin";
  }

  if (clean === "insyt manager") {
    return "INSYT Manager";
  }

  if (clean === "client admin") {
    return "Client Admin";
  }

  if (clean === "client") {
    return "Client";
  }

  if (clean === "reviewer") {
    return "Reviewer";
  }

  return role;
}

function hasProject(
  user: AccessUser,
  projectKey: string
) {
  return (user.project_access || []).includes(
    projectKey
  );
}

function ProjectStaffingContent() {
  const [currentUser, setCurrentUser] =
    useState<StoredUser | null>(null);

  const [users, setUsers] =
    useState<AccessUser[]>([]);

  const [projects, setProjects] =
    useState<ProjectRow[]>([]);

  const [loading, setLoading] =
    useState(true);

  const [saving, setSaving] =
    useState(false);

  const [message, setMessage] =
    useState("");

  const [
    selectedProjectKey,
    setSelectedProjectKey,
  ] = useState("");

  const [
    originalSelection,
    setOriginalSelection,
  ] = useState<Set<string>>(
    new Set()
  );

  const [
    draftSelection,
    setDraftSelection,
  ] = useState<Set<string>>(
    new Set()
  );

  const [projectSearch, setProjectSearch] =
    useState("");

  const [nameSearch, setNameSearch] =
    useState("");

  const [roleFilter, setRoleFilter] =
    useState("");

  const [statusFilter, setStatusFilter] =
    useState("");

  const [groupFilter, setGroupFilter] =
    useState("");

  const [scoreMin, setScoreMin] =
    useState("");

  const [scoreMax, setScoreMax] =
    useState("");

  const [
    copyFromProject,
    setCopyFromProject,
  ] = useState("");

  useEffect(() => {
    const storedUser =
      localStorage.getItem("insyt_user");

    if (storedUser) {
      try {
        setCurrentUser(
          JSON.parse(storedUser)
        );
      } catch {
        setCurrentUser(null);
      }
    }
  }, []);

  useEffect(() => {
    loadPage();
  }, []);

  async function loadPage() {
    setLoading(true);
    setMessage("");

    try {
      const [
        userResponse,
        projectRows,
      ] = await Promise.all([
        apiGet("/api/users/"),
        loadProjectTree(),
      ]);

      const nextUsers: AccessUser[] =
        Array.isArray(userResponse)
          ? userResponse
          : userResponse?.users || [];

      setUsers(nextUsers);
      setProjects(projectRows);
    } catch (error) {
      console.error(error);

      setMessage(
        "Unable to load Project Staffing."
      );
    } finally {
      setLoading(false);
    }
  }

  async function loadProjectTree() {
    const rows: ProjectRow[] = [];

    await Promise.all(
      workspaces.map(async (workspace) => {
        try {
          const clientResponse: any =
            await apiGet(
              `/api/${workspace.value}/clients`
            );

          const clients: string[] =
            clientResponse?.clients || [];

          await Promise.all(
            clients.map(
              async (client) => {
                try {
                  const projectResponse: any =
                    await apiGet(
                      `/api/${workspace.value}/clients/${encodeURIComponent(
                        client
                      )}/projects`
                    );

                  const projectNames:
                    | string[] =
                    projectResponse?.projects ||
                    [];

                  projectNames.forEach(
                    (project) => {
                      rows.push({
                        workspace:
                          workspace.value,
                        workspaceLabel:
                          workspace.label,
                        client,
                        project,
                        projectKey:
                          makeProjectKey(
                            workspace.value,
                            client,
                            project
                          ),
                      });
                    }
                  );
                } catch (error) {
                  console.error(
                    error
                  );
                }
              }
            )
          );
        } catch (error) {
          console.error(error);
        }
      })
    );

    return rows.sort((a, b) => {
      const workspaceCompare =
        a.workspace.localeCompare(
          b.workspace
        );

      if (workspaceCompare !== 0) {
        return workspaceCompare;
      }

      const clientCompare =
        a.client.localeCompare(
          b.client
        );

      if (clientCompare !== 0) {
        return clientCompare;
      }

      return a.project.localeCompare(
        b.project
      );
    });
  }

  const selectedProject =
    useMemo(() => {
      return (
        projects.find(
          (project) =>
            project.projectKey ===
            selectedProjectKey
        ) || null
      );
    }, [
      projects,
      selectedProjectKey,
    ]);

  function chooseProject(
    projectKey: string
  ) {
    setSelectedProjectKey(
      projectKey
    );

    const assigned = new Set(
      users
        .filter((user) =>
          hasProject(
            user,
            projectKey
          )
        )
        .map(
          (user) => user.username
        )
    );

    setOriginalSelection(
      new Set(assigned)
    );

    setDraftSelection(
      new Set(assigned)
    );

    setMessage("");
    setCopyFromProject("");
  }

  const filteredProjects =
    useMemo(() => {
      const search =
        projectSearch
          .trim()
          .toLowerCase();

      if (!search) {
        return projects;
      }

      return projects.filter(
        (project) => {
          return (
            project.workspaceLabel
              .toLowerCase()
              .includes(search) ||
            project.workspace
              .toLowerCase()
              .includes(search) ||
            project.client
              .toLowerCase()
              .includes(search) ||
            project.project
              .toLowerCase()
              .includes(search)
          );
        }
      );
    }, [
      projects,
      projectSearch,
    ]);

  const roleOptions =
    useMemo(() => {
      return Array.from(
        new Set(
          users
            .map((user) =>
              normalizeRole(user.role)
            )
            .filter(Boolean)
        )
      ).sort((a, b) =>
        a.localeCompare(b)
      );
    }, [users]);

  const statusOptions =
    useMemo(() => {
      return Array.from(
        new Set(
          users
            .map(
              (user) =>
                user.status
            )
            .filter(Boolean)
        )
      ).sort((a, b) =>
        a.localeCompare(b)
      );
    }, [users]);

  const groupOptions =
  useMemo(() => {
    return Array.from(
      new Set(
        users.flatMap(
          (user) =>
            user.staffing_groups ||
            []
        )
      )
    ).sort((a, b) =>
      a.localeCompare(b)
    );
  }, [users]);

  const filteredUsers =
    useMemo(() => {
      const nameNeedle =
        nameSearch
          .trim()
          .toLowerCase();

      const minimumScore =
        scoreMin === ""
          ? null
          : Number(scoreMin);

      const maximumScore =
        scoreMax === ""
          ? null
          : Number(scoreMax);

      return users.filter(
        (user) => {
          const displayName =
            String(
              user.display_name ||
                ""
            ).toLowerCase();

          const username =
            String(
              user.username || ""
            ).toLowerCase();

          const email =
            String(
              user.email || ""
            ).toLowerCase();

          if (
            nameNeedle &&
            !displayName.includes(
              nameNeedle
            ) &&
            !username.includes(
              nameNeedle
            ) &&
            !email.includes(
              nameNeedle
            )
          ) {
            return false;
          }

          if (
            roleFilter &&
            normalizeRole(
              user.role
            ) !== roleFilter
          ) {
            return false;
          }

          if (
            statusFilter &&
            user.status !==
              statusFilter
          ) {
            return false;
          }

          if (
            groupFilter &&
            !(
              user.staffing_groups ||
              []
            ).includes(
              groupFilter
            )
          ) {
            return false;
          }

          const score =
            user.performance_score;

          if (
            minimumScore !== null &&
            (
              score === null ||
              score === undefined ||
              score <
                minimumScore
            )
          ) {
            return false;
          }

          if (
            maximumScore !== null &&
            (
              score === null ||
              score === undefined ||
              score >
                maximumScore
            )
          ) {
            return false;
          }

          return true;
        }
      );
    }, [
      users,
      nameSearch,
      roleFilter,
      statusFilter,
      groupFilter,
      scoreMin,
      scoreMax,
    ]);

  const currentlyStaffedCount =
    useMemo(() => {
      if (!selectedProjectKey) {
        return 0;
      }

      return users.filter(
        (user) =>
          hasProject(
            user,
            selectedProjectKey
          )
      ).length;
    }, [
      users,
      selectedProjectKey,
    ]);

  function toggleUser(
    username: string
  ) {
    setDraftSelection(
      (current) => {
        const next =
          new Set(current);

        if (
          next.has(username)
        ) {
          next.delete(username);
        } else {
          next.add(username);
        }

        return next;
      }
    );
  }

  function selectAllFiltered() {
    setDraftSelection(
      (current) => {
        const next =
          new Set(current);

        filteredUsers.forEach(
          (user) => {
            next.add(
              user.username
            );
          }
        );

        return next;
      }
    );
  }

  function clearFilteredSelection() {
    setDraftSelection(
      (current) => {
        const next =
          new Set(current);

        filteredUsers.forEach(
          (user) => {
            next.delete(
              user.username
            );
          }
        );

        return next;
      }
    );
  }

  function clearAllSelection() {
    setDraftSelection(
      new Set()
    );
  }

  function restoreOriginalSelection() {
    setDraftSelection(
      new Set(
        originalSelection
      )
    );
  }

  function copyProjectStaffing() {
    if (!copyFromProject) {
      return;
    }

    const copiedUsers =
      users
        .filter((user) =>
          hasProject(
            user,
            copyFromProject
          )
        )
        .map(
          (user) =>
            user.username
        );

    setDraftSelection(
      (current) => {
        const next =
          new Set(current);

        copiedUsers.forEach(
          (username) => {
            next.add(
              username
            );
          }
        );

        return next;
      }
    );

    setMessage(
      `Added ${copiedUsers.length} user(s) from the selected project to the draft staffing roster.`
    );
  }

  function clearFilters() {
    setNameSearch("");
    setRoleFilter("");
    setStatusFilter("");
    setGroupFilter("");
    setScoreMin("");
    setScoreMax("");
  }

  async function saveStaffing() {
    if (!selectedProjectKey) {
      setMessage(
        "Select a project before saving staffing."
      );
      return;
    }

    const assign =
      Array.from(
        draftSelection
      ).filter(
        (username) =>
          !originalSelection.has(
            username
          )
      );

    const remove =
      Array.from(
        originalSelection
      ).filter(
        (username) =>
          !draftSelection.has(
            username
          )
      );

    if (
      assign.length === 0 &&
      remove.length === 0
    ) {
      setMessage(
        "No staffing changes to save."
      );
      return;
    }

    const confirmed =
      window.confirm(
        `Save Project Staffing?\n\nAdd: ${assign.length}\nRemove: ${remove.length}`
      );

    if (!confirmed) {
      return;
    }

    setSaving(true);
    setMessage("");

    try {
      const response: BulkResponse =
        await apiPost(
          "/api/users/project-access/bulk",
          {
            project_id:
              selectedProjectKey,
            assign,
            remove,
          }
        );

      const assignedCount =
        response.assigned_count ||
        0;

      const removedCount =
        response.removed_count ||
        0;

      const unchangedCount =
        response.unchanged_count ||
        0;

      setMessage(
        `Project Staffing saved. Added ${assignedCount}, removed ${removedCount}, unchanged ${unchangedCount}.`
      );

      const refreshed: any =
        await apiGet(
          "/api/users/"
        );

      const nextUsers:
        AccessUser[] =
        Array.isArray(refreshed)
          ? refreshed
          : refreshed?.users ||
            [];

      setUsers(nextUsers);

      const assigned =
        new Set(
          nextUsers
            .filter((user) =>
              hasProject(
                user,
                selectedProjectKey
              )
            )
            .map(
              (user) =>
                user.username
            )
        );

      setOriginalSelection(
        new Set(assigned)
      );

      setDraftSelection(
        new Set(assigned)
      );
    } catch (error: any) {
      console.error(error);

      const detail =
        error?.detail ||
        error?.message ||
        "Project Staffing save failed.";

      setMessage(
        typeof detail ===
          "string"
          ? detail
          : JSON.stringify(
              detail
            )
      );
    } finally {
      setSaving(false);
    }
  }

  const additions =
    useMemo(() => {
      return Array.from(
        draftSelection
      ).filter(
        (username) =>
          !originalSelection.has(
            username
          )
      ).length;
    }, [
      draftSelection,
      originalSelection,
    ]);

  const removals =
    useMemo(() => {
      return Array.from(
        originalSelection
      ).filter(
        (username) =>
          !draftSelection.has(
            username
          )
      ).length;
    }, [
      draftSelection,
      originalSelection,
    ]);

  if (loading) {
    return (
      <AppShell>
        <PageContainer>
          <p className="text-slate-400">
            Loading Project Staffing...
          </p>
        </PageContainer>
      </AppShell>
    );
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Project Staffing"
          subtitle="Select a project, filter the available user population, and assign or remove project staff in bulk."
        />

        {message && (
          <div className="mb-6 rounded-xl border border-sky-500/30 bg-sky-500/10 px-4 py-3 text-sm text-sky-200">
            {message}
          </div>
        )}

        <ContentCard title="Select Project">
          <div className="mb-4">
            <input
              value={projectSearch}
              onChange={(event) =>
                setProjectSearch(
                  event.target.value
                )
              }
              placeholder="Search client, workspace, or project..."
              className="w-full max-w-2xl rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
            />
          </div>

          <div className="max-h-[340px] overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="sticky top-0 z-10 bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left">
                    Select
                  </th>

                  <th className="p-3 text-left">
                    Client
                  </th>

                  <th className="p-3 text-left">
                    Workspace
                  </th>

                  <th className="p-3 text-left">
                    Project
                  </th>

                  <th className="p-3 text-left">
                    Staffed Users
                  </th>
                </tr>
              </thead>

              <tbody>
                {filteredProjects.map(
                  (project) => {
                    const staffed =
                      users.filter(
                        (user) =>
                          hasProject(
                            user,
                            project.projectKey
                          )
                      ).length;

                    const selected =
                      project.projectKey ===
                      selectedProjectKey;

                    return (
                      <tr
                        key={
                          project.projectKey
                        }
                        className={
                          selected
                            ? "border-t border-slate-800 bg-teal-500/10"
                            : "border-t border-slate-800 hover:bg-slate-900/60"
                        }
                      >
                        <td className="p-3">
                          <input
                            type="radio"
                            name="project-staffing-project"
                            checked={
                              selected
                            }
                            onChange={() =>
                              chooseProject(
                                project.projectKey
                              )
                            }
                            className="accent-teal-500"
                          />
                        </td>

                        <td className="p-3 text-slate-200">
                          {prettyName(
                            project.client
                          )}
                        </td>

                        <td className="p-3 text-slate-300">
                          {
                            project.workspaceLabel
                          }
                        </td>

                        <td className="p-3 font-medium text-white">
                          {prettyName(
                            project.project
                          )}
                        </td>

                        <td className="p-3 text-slate-300">
                          {staffed}
                        </td>
                      </tr>
                    );
                  }
                )}

                {filteredProjects.length ===
                  0 && (
                  <tr>
                    <td
                      colSpan={5}
                      className="p-6 text-center text-slate-500"
                    >
                      No projects found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>

        {selectedProject && (
          <div className="mt-6">
            <ContentCard
              title={`Staff Project: ${prettyName(
                selectedProject.project
              )}`}
            >
              <div className="mb-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="grid grid-cols-1 gap-3 md:grid-cols-4">
                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">
                      Client
                    </div>

                    <div className="mt-1 font-medium text-white">
                      {prettyName(
                        selectedProject.client
                      )}
                    </div>
                  </div>

                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">
                      Workspace
                    </div>

                    <div className="mt-1 font-medium text-white">
                      {
                        selectedProject.workspaceLabel
                      }
                    </div>
                  </div>

                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">
                      Current Staff
                    </div>

                    <div className="mt-1 font-medium text-white">
                      {
                        currentlyStaffedCount
                      }
                    </div>
                  </div>

                  <div>
                    <div className="text-xs uppercase tracking-wide text-slate-500">
                      Draft Staff
                    </div>

                    <div className="mt-1 font-medium text-white">
                      {
                        draftSelection.size
                      }
                    </div>
                  </div>
                </div>
              </div>

              <div className="mb-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="mb-3 text-sm font-semibold text-white">
                  Copy Staffing From Project
                </div>

                <div className="flex flex-col gap-3 lg:flex-row">
                  <select
                    value={
                      copyFromProject
                    }
                    onChange={(event) =>
                      setCopyFromProject(
                        event.target.value
                      )
                    }
                    className="min-w-0 flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
                  >
                    <option value="">
                      Select source project...
                    </option>

                    {projects
                      .filter(
                        (project) =>
                          project.projectKey !==
                          selectedProjectKey
                      )
                      .map(
                        (project) => (
                          <option
                            key={
                              project.projectKey
                            }
                            value={
                              project.projectKey
                            }
                          >
                            {
                              project.workspaceLabel
                            }{" "}
                            /{" "}
                            {prettyName(
                              project.client
                            )}{" "}
                            /{" "}
                            {prettyName(
                              project.project
                            )}
                          </option>
                        )
                      )}
                  </select>

                  <Button
                    variant="secondary"
                    onClick={
                      copyProjectStaffing
                    }
                  >
                    Add Copied Team
                  </Button>
                </div>
              </div>

              <div className="mb-5 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="mb-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
                  <input
                    value={nameSearch}
                    onChange={(event) =>
                      setNameSearch(
                        event.target.value
                      )
                    }
                    placeholder="Search name, email, username"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
                  />

                  <select
                    value={roleFilter}
                    onChange={(event) =>
                      setRoleFilter(
                        event.target.value
                      )
                    }
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  >
                    <option value="">
                      All Levels
                    </option>

                    {roleOptions.map(
                      (role) => (
                        <option
                          key={role}
                          value={role}
                        >
                          {role}
                        </option>
                      )
                    )}
                  </select>

                  <select
                    value={groupFilter}
                    onChange={(event) =>
                      setGroupFilter(
                        event.target.value
                      )
                    }
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  >
                    <option value="">
                      All Groups
                    </option>

                    {groupOptions.map(
                      (group) => (
                        <option
                          key={group}
                          value={group}
                        >
                          Group {group}
                        </option>
                      )
                    )}
                  </select>

                  <select
                    value={statusFilter}
                    onChange={(event) =>
                      setStatusFilter(
                        event.target.value
                      )
                    }
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
                  >
                    <option value="">
                      All Statuses
                    </option>

                    {statusOptions.map(
                      (status) => (
                        <option
                          key={status}
                          value={status}
                        >
                          {status}
                        </option>
                      )
                    )}
                  </select>

                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={scoreMin}
                    onChange={(event) =>
                      setScoreMin(
                        event.target.value
                      )
                    }
                    placeholder="Overall Score Min"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
                  />

                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={scoreMax}
                    onChange={(event) =>
                      setScoreMax(
                        event.target.value
                      )
                    }
                    placeholder="Overall Score Max"
                    className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white outline-none focus:border-sky-500"
                  />

                  <button
                    type="button"
                    onClick={clearFilters}
                    className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
                  >
                    Clear Filters
                  </button>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <Button
                    variant="secondary"
                    onClick={
                      selectAllFiltered
                    }
                  >
                    Select All Filtered
                  </Button>

                  <Button
                    variant="secondary"
                    onClick={
                      clearFilteredSelection
                    }
                  >
                    Clear Filtered Selection
                  </Button>

                  <Button
                    variant="secondary"
                    onClick={
                      restoreOriginalSelection
                    }
                  >
                    Restore Saved Roster
                  </Button>

                  <Button
                    variant="danger"
                    onClick={
                      clearAllSelection
                    }
                  >
                    Clear All
                  </Button>
                </div>

                <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-slate-400">
                  <span>
                    Showing{" "}
                    {
                      filteredUsers.length
                    }{" "}
                    of {users.length} users
                  </span>

                  <span>
                    Selected:{" "}
                    {
                      draftSelection.size
                    }
                  </span>

                  <span className="text-emerald-300">
                    Pending Add:{" "}
                    {additions}
                  </span>

                  <span className="text-red-300">
                    Pending Remove:{" "}
                    {removals}
                  </span>
                </div>
              </div>

              <div className="max-h-[65vh] overflow-auto rounded-xl border border-slate-800">
                <table className="w-full text-sm">
                  <thead className="sticky top-0 z-20 bg-slate-900 text-slate-400">
                    <tr>
                      <th className="p-3 text-left">
                        Staff
                      </th>

                      <th className="p-3 text-left">
                        Name
                      </th>

                      <th className="p-3 text-left">
                        Level
                      </th>

                      <th className="p-3 text-left">
                        Group
                      </th>

                      <th className="p-3 text-right">
                        Overall Score
                      </th>

                      <th className="p-3 text-left">
                        Status
                      </th>

                      <th className="p-3 text-left">
                        Assigned
                      </th>
                    </tr>
                  </thead>

                  <tbody>
                    {filteredUsers.map(
                      (user) => {
                        const checked =
                          draftSelection.has(
                            user.username
                          );

                        const originallyAssigned =
                          originalSelection.has(
                            user.username
                          );

                        const pendingAdd =
                          checked &&
                          !originallyAssigned;

                        const pendingRemove =
                          !checked &&
                          originallyAssigned;

                        return (
                          <tr
                            key={
                              user.username
                            }
                            className={
                              pendingAdd
                                ? "border-t border-slate-800 bg-emerald-500/5"
                                : pendingRemove
                                  ? "border-t border-slate-800 bg-red-500/5"
                                  : "border-t border-slate-800"
                            }
                          >
                            <td className="p-3">
                              <input
                                type="checkbox"
                                checked={
                                  checked
                                }
                                onChange={() =>
                                  toggleUser(
                                    user.username
                                  )
                                }
                                className="accent-teal-500"
                              />
                            </td>

                            <td className="p-3">
                              <div className="font-medium text-white">
                                {user.display_name ||
                                  user.username}
                              </div>

                              <div className="text-xs text-slate-500">
                                {user.email ||
                                  user.username}
                              </div>
                            </td>

                            <td className="p-3 text-slate-300">
                              {normalizeRole(
                                user.role
                              )}
                            </td>

                            <td className="p-3 text-slate-300">
                              {(user.staffing_groups || [])
                                .length > 0
                                ? (
                                    user.staffing_groups ||
                                    []
                                  ).join(", ")
                                : "—"}
                            </td>

                            <td className="p-3 text-right font-semibold text-white">
                              {user.performance_score ===
                                null ||
                              user.performance_score ===
                                undefined
                                ? "N/A"
                                : user.performance_score}
                            </td>

                            <td className="p-3">
                              <span
                                className={
                                  String(
                                    user.status
                                  ).toLowerCase() ===
                                  "active"
                                    ? "rounded-full bg-emerald-500/10 px-3 py-1 text-xs text-emerald-300"
                                    : "rounded-full bg-red-500/10 px-3 py-1 text-xs text-red-300"
                                }
                              >
                                {user.status ||
                                  "Unknown"}
                              </span>
                            </td>

                            <td className="p-3">
                              {pendingAdd ? (
                                <span className="text-emerald-300">
                                  Pending Add
                                </span>
                              ) : pendingRemove ? (
                                <span className="text-red-300">
                                  Pending Remove
                                </span>
                              ) : originallyAssigned ? (
                                <span className="text-sky-300">
                                  Yes
                                </span>
                              ) : (
                                <span className="text-slate-500">
                                  No
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      }
                    )}

                    {filteredUsers.length ===
                      0 && (
                      <tr>
                        <td
                          colSpan={7}
                          className="p-8 text-center text-slate-500"
                        >
                          No users match the current filters.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>

              <div className="mt-6 flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
                <div className="text-sm text-slate-300">
                  Draft roster:{" "}
                  <span className="font-semibold text-white">
                    {
                      draftSelection.size
                    }
                  </span>
                  {" · "}
                  <span className="text-emerald-300">
                    +{additions}
                  </span>
                  {" · "}
                  <span className="text-red-300">
                    -{removals}
                  </span>
                </div>

                <Button
                  onClick={
                    saveStaffing
                  }
                  disabled={
                    saving ||
                    (additions === 0 &&
                      removals === 0)
                  }
                >
                  {saving
                    ? "Saving Project Staffing..."
                    : "Save Project Staffing"}
                </Button>
              </div>
            </ContentCard>
          </div>
        )}
      </PageContainer>
    </AppShell>
  );
}

export default function ProjectStaffingPage() {
  return (
    <Suspense
      fallback={
        <div>
          Loading Project Staffing...
        </div>
      }
    >
      <ProjectStaffingContent />
    </Suspense>
  );
}