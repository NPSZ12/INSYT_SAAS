"use client";

import {
  Suspense,
  useCallback,
  useEffect,
  useMemo,
  useState,
} from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../../components/AppShell";
import PageContainer from "../../../components/PageContainer";
import PageHeader from "../../../components/PageHeader";
import ContentCard from "../../../components/ContentCard";
import CyberUtilityWorkflowNav from "../../../components/CyberUtilityWorkflowNav";
import { apiGet, apiPost } from "../../../lib/api";

type Workspace = "capture" | "discovery";
type Status = "pending" | "approved";

type Entity = {
  entity_id: string;
  status: Status;
  raw_ucids: string[];
  raw_count: number;
};

type MembershipResponse = {
  workspace: Workspace;
  client: string;
  project: string;
  revision: number;
  entity_count: number;
  raw_inventory_count: number;
  entities: Entity[];
};

type OperationResponse = {
  status: string;
  revision: number;
  entity_count: number;
};

type StatusFilter = "all" | Status;
type SortField = "entity_id" | "status" | "raw_count";

function getMessage(error: unknown): string {
  return error instanceof Error
    ? error.message
    : "Unexpected Cyber² request failure.";
}

function MergeDedupeContent() {
  const params = useSearchParams();

  const workspace: Workspace =
    params.get("workspace") === "discovery"
      ? "discovery"
      : "capture";

  const client = params.get("client") || "";
  const project = params.get("project") || "";

  const [data, setData] = useState<MembershipResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState<StatusFilter>("all");
  const [sortField, setSortField] = useState<SortField>("entity_id");
  const [descending, setDescending] = useState(false);

  const [selected, setSelected] = useState<string[]>([]);
  const [targetId, setTargetId] = useState("");

  const [newEntityId, setNewEntityId] = useState("");
  const [newRawIds, setNewRawIds] = useState("");

  const scope = useMemo(() => ({
    client,
    project,
  }), [client, project]);

  const basePath = `/api/${workspace}/cyber2/entity-membership`;

  const refresh = useCallback(async () => {
    if (!client || !project) {
      setData(null);
      setError("Select a client and project before loading Cyber².");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const query = new URLSearchParams(scope);
      const response = await apiGet(
        `${basePath}?${query.toString()}`
      ) as MembershipResponse;

      if (
        !Array.isArray(response.entities) ||
        !Number.isInteger(response.revision)
      ) {
        throw new Error("Invalid membership API response.");
      }

      setData(response);

      const ids = new Set(
        response.entities.map((item) => item.entity_id)
      );

      setSelected((previous) =>
        previous.filter((id) => ids.has(id))
      );

      setTargetId((previous) =>
        ids.has(previous) ? previous : ""
      );
    } catch (reason) {
      setData(null);
      setError(getMessage(reason));
    } finally {
      setLoading(false);
    }
  }, [basePath, client, project, scope]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const entities = useMemo(() => {
    const query = search.trim().toLowerCase();

    return [...(data?.entities || [])]
      .filter((entity) =>
        (filter === "all" || entity.status === filter) &&
        (
          !query ||
          entity.entity_id.toLowerCase().includes(query) ||
          entity.raw_ucids.some((ucid) =>
            ucid.toLowerCase().includes(query)
          )
        )
      )
      .sort((a, b) => {
        const comparison =
          sortField === "raw_count"
            ? a.raw_count - b.raw_count
            : String(a[sortField]).localeCompare(
                String(b[sortField])
              );

        return descending ? -comparison : comparison;
      });
  }, [data, search, filter, sortField, descending]);

  function toggleSelected(entityId: string) {
    setSelected((previous) =>
      previous.includes(entityId)
        ? previous.filter((id) => id !== entityId)
        : [...previous, entityId]
    );
  }

  async function mutate(
    operation: "register" | "approve" | "merge" | "reverse-last-merge",
    payload: Record<string, unknown>,
    confirmation: string
  ) {
    if (!data || busy) return;

    if (!window.confirm(confirmation)) return;

    setBusy(true);
    setError("");
    setMessage("");

    try {
      const response = await apiPost(
        `${basePath}/${operation}`,
        {
          ...scope,
          ...payload,
          expected_revision: data.revision,
        }
      ) as OperationResponse;

      if (
        response.status !== "saved" ||
        response.revision !== data.revision + 1
      ) {
        throw new Error(
          "Unexpected registry revision. Reload before proceeding."
        );
      }

      setMessage(
        `Operation saved. Registry revision ${response.revision}.`
      );

      if (operation === "register") {
        setNewEntityId("");
        setNewRawIds("");
      }

      setSelected([]);
      setTargetId("");

      await refresh();
    } catch (reason) {
      const operationError = getMessage(reason);

      // Never retry a mutation automatically.
      // Reload the authoritative revision, then preserve the error.
      await refresh();

      setError(
        `${operationError} Review the current registry before retrying.`
      );
    } finally {
      setBusy(false);
    }
  }

  function register() {
    const entityId = newEntityId.trim();
    const rawUCIDs = Array.from(
      new Set(
        newRawIds
          .split(/[\s,;]+/)
          .map((id) => id.trim())
          .filter(Boolean)
      )
    );

    if (!entityId || rawUCIDs.length === 0) {
      setError("Enter an entity ID and at least one RAW UCID.");
      return;
    }

    void mutate(
      "register",
      {
        entity_id: entityId,
        raw_ucids: rawUCIDs,
      },
      `Register ${rawUCIDs.length} RAW record(s) under ${entityId} as pending?`
    );
  }

  function approve(entityId: string) {
    void mutate(
      "approve",
      {
        entity_id: entityId,
        note: "Approved through Cyber² Merge & Dedupe",
      },
      `Approve membership for ${entityId}?`
    );
  }

  function merge() {
    if (!targetId) {
      setError("Select an approved target entity.");
      return;
    }

    const sources = selected.filter((id) => id !== targetId);

    if (!sources.length) {
      setError("Select at least one different source entity.");
      return;
    }

    const byId = new Map(
      (data?.entities || []).map((entity) => [
        entity.entity_id,
        entity,
      ])
    );

    if (
      byId.get(targetId)?.status !== "approved" ||
      sources.some((id) => byId.get(id)?.status !== "approved")
    ) {
      setError("Only approved entities can be merged.");
      return;
    }

    void mutate(
      "merge",
      {
        target_entity_id: targetId,
        source_entity_ids: sources,
        note: "Reviewer-confirmed merge through Cyber²",
      },
      `Merge ${sources.join(", ")} into ${targetId}? This must represent the same verified individual.`
    );
  }

  function reverseMerge() {
    void mutate(
      "reverse-last-merge",
      {},
      "Reverse the most recent merge in this project? This restores the previous entity memberships."
    );
  }

  function changeSort(field: SortField) {
    if (field === sortField) {
      setDescending((previous) => !previous);
    } else {
      setSortField(field);
      setDescending(false);
    }
  }

  const approvedCount = data?.entities.filter(
    (entity) => entity.status === "approved"
  ).length || 0;

  const canEdit = Boolean(data) && !busy && !loading;

  return (
    <AppShell>
      <PageContainer>
        <CyberUtilityWorkflowNav />

        <PageHeader
          title="Merge & Dedupe"
          subtitle="Review project-scoped identities, validate membership, and preserve original RAW evidence."
        />

        <div className="mb-5 grid grid-cols-1 gap-3 rounded-xl border border-slate-800 bg-slate-900 p-4 md:grid-cols-3">
          <div>
            <div className="text-xs text-slate-400">Workspace</div>
            <div className="font-semibold text-slate-100">{workspace}</div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Client</div>
            <div className="font-semibold text-slate-100">
              {client || "Not selected"}
            </div>
          </div>
          <div>
            <div className="text-xs text-slate-400">Project</div>
            <div className="font-semibold text-sky-300">
              {project || "Not selected"}
            </div>
          </div>
        </div>

        <div className="mb-5 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ["RAW inventory", data?.raw_inventory_count ?? "—"],
            ["Entities", data?.entity_count ?? "—"],
            ["Approved", data ? approvedCount : "—"],
            ["Revision", data?.revision ?? "—"],
          ].map(([label, value]) => (
            <div
              key={String(label)}
              className="rounded-xl border border-slate-800 bg-slate-900 p-4"
            >
              <div className="text-xs text-slate-400">{label}</div>
              <div className="mt-1 text-xl font-bold text-slate-100">
                {value}
              </div>
            </div>
          ))}
        </div>

        {error && (
          <div
            role="alert"
            className="mb-4 rounded-lg border border-rose-700 bg-rose-950/30 p-3 text-sm text-rose-300"
          >
            {error}
          </div>
        )}

        {message && (
          <div
            role="status"
            className="mb-4 rounded-lg border border-slate-700 p-3 text-sm text-slate-200"
          >
            {message}
          </div>
        )}

        <ContentCard title="Project identity registry">
          <div className="mb-4 flex flex-wrap items-center gap-3">
            <input
              aria-label="Search entity ID or UCID"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="Search entity ID or UCID"
              className="min-w-[220px] flex-1 rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            />

            <select
              aria-label="Filter by approval status"
              value={filter}
              onChange={(event) =>
                setFilter(event.target.value as StatusFilter)
              }
              className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
            >
              <option value="all">All statuses</option>
              <option value="approved">Approved</option>
              <option value="pending">Pending</option>
            </select>

            <button
              type="button"
              disabled={busy || loading}
              onClick={() => void refresh()}
              className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-100 disabled:opacity-50"
            >
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>

          <div className="overflow-x-auto rounded-lg border border-slate-800">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-900 text-slate-300">
                <tr>
                  <th className="p-3">Select</th>
                  <th className="p-3">
                    <button type="button" onClick={() => changeSort("entity_id")}>
                      Entity ID
                    </button>
                  </th>
                  <th className="p-3">
                    <button type="button" onClick={() => changeSort("status")}>
                      Status
                    </button>
                  </th>
                  <th className="p-3">
                    <button type="button" onClick={() => changeSort("raw_count")}>
                      RAW members
                    </button>
                  </th>
                  <th className="p-3">Action</th>
                </tr>
              </thead>
              <tbody>
                {entities.map((entity) => (
                  <tr
                    key={entity.entity_id}
                    className="border-t border-slate-800 text-slate-200"
                  >
                    <td className="p-3">
                      <input
                        type="checkbox"
                        aria-label={`Select ${entity.entity_id}`}
                        checked={selected.includes(entity.entity_id)}
                        onChange={() => toggleSelected(entity.entity_id)}
                      />
                    </td>
                    <td className="p-3 font-medium">
                      {entity.entity_id}
                    </td>
                    <td className="p-3">{entity.status}</td>
                    <td className="p-3">{entity.raw_count}</td>
                    <td className="p-3">
                      {entity.status === "pending" ? (
                        <button
                          type="button"
                          disabled={!canEdit}
                          onClick={() => approve(entity.entity_id)}
                          className="rounded-lg border border-sky-700 px-3 py-1.5 text-sky-300 disabled:opacity-50"
                        >
                          Approve
                        </button>
                      ) : (
                        <span className="text-slate-500">Approved</span>
                      )}
                    </td>
                  </tr>
                ))}
                {entities.length === 0 && (
                  <tr>
                    <td colSpan={5} className="p-6 text-center text-slate-400">
                      {loading ? "Loading identities..." : "No matching entities."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>

        <div className="mt-5 grid grid-cols-1 gap-5 xl:grid-cols-2">
          <ContentCard title="Register RAW membership">
            <p className="mb-3 text-sm text-slate-400">
              Register reviewer-selected RAW UCIDs as a pending entity.
              No automatic identity assignment is performed.
            </p>

            <input
              value={newEntityId}
              onChange={(event) => setNewEntityId(event.target.value)}
              placeholder="New entity ID"
              aria-label="New entity ID"
              className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
            />

            <textarea
              value={newRawIds}
              onChange={(event) => setNewRawIds(event.target.value)}
              placeholder="RAW UCIDs (one per line)"
              aria-label="RAW UCIDs"
              rows={4}
              className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
            />

            <button
              type="button"
              disabled={!canEdit}
              onClick={register}
              className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Register pending entity
            </button>
          </ContentCard>

          <ContentCard title="Reviewer-controlled merge">
            <p className="mb-3 text-sm text-slate-400">
              Select source entities in the table, then choose an approved
              target. Confirm that all records belong to the same person
              before merging.
            </p>

            <select
              value={targetId}
              onChange={(event) => setTargetId(event.target.value)}
              aria-label="Merge target entity"
              className="mb-3 w-full rounded-lg border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
            >
              <option value="">Choose target entity</option>
              {(data?.entities || [])
                .filter((entity) => entity.status === "approved")
                .map((entity) => (
                  <option key={entity.entity_id} value={entity.entity_id}>
                    {entity.entity_id}
                  </option>
                ))}
            </select>

            <div className="mb-4 text-sm text-slate-400">
              Selected entities: {selected.length}
            </div>

            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                disabled={!canEdit}
                onClick={merge}
                className="rounded-lg bg-sky-700 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Merge selected entities
              </button>

              <button
                type="button"
                disabled={!canEdit}
                onClick={reverseMerge}
                className="rounded-lg border border-amber-700 px-4 py-2 text-sm font-semibold text-amber-300 disabled:opacity-50"
              >
                Reverse last merge
              </button>
            </div>
          </ContentCard>
        </div>

        <p className="mt-5 text-xs text-slate-500">
          RAW source records remain immutable. Registry revisions protect
          against stale updates. Conflicting identifiers must be reviewed
          before any merge. Administrator approval is required by the API.
        </p>
      </PageContainer>
    </AppShell>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<div>Loading Cyber²...</div>}>
      <MergeDedupeContent />
    </Suspense>
  );
}