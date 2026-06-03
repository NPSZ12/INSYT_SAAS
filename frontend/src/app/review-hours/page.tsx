"use client";

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";

import AppShell from "../../components/AppShell";
import PageContainer from "../../components/PageContainer";
import PageHeader from "../../components/PageHeader";
import ContentCard from "../../components/ContentCard";
import Button from "../../components/Button";
import { apiGet, apiPost } from "../../lib/api";

type TimeEntryDetail = {
  entry_id?: string;
  date: string;
  login?: string;
  logout?: string;
  break_minutes?: number;
  hours?: number;
  notes?: string;
  source?: string;
  edited_by?: string;
  edited_at?: string;
};

type ReviewHoursRow = {
  username: string;
  display_name: string;
  role: string;
  mon_hours: number;
  tue_hours: number;
  wed_hours: number;
  thu_hours: number;
  fri_hours: number;
  sat_hours: number;
  sun_hours: number;
  week_total: number;
  details: TimeEntryDetail[];
};

type StoredUser = {
  username: string;
  display_name?: string;
  role: string;
};

function prettyWorkspace(workspace: string) {
  if (workspace === "capture") return "INSYT Capture";
  if (workspace === "discovery") return "INSYT Discovery";
  if (workspace === "summaries") return "INSYT Summaries";
  if (workspace === "development") return "INSYT Development";

  return workspace || "Workspace";
}

function getMonday(date: Date) {
  const copy = new Date(date);
  const day = copy.getDay();
  const diff = copy.getDate() - day + (day === 0 ? -6 : 1);

  copy.setDate(diff);
  copy.setHours(0, 0, 0, 0);

  return copy;
}

function formatDate(date: Date) {
  return date.toISOString().slice(0, 10);
}

function addDays(date: Date, days: number) {
  const copy = new Date(date);
  copy.setDate(copy.getDate() + days);
  return copy;
}

function formatDisplayDate(dateString: string) {
  const date = new Date(`${dateString}T00:00:00`);

  return date.toLocaleDateString("en-US", {
    month: "2-digit",
    day: "2-digit",
    year: "numeric",
  });
}

function buildWeekOptions(count = 26) {
  const currentMonday = getMonday(new Date());

  return Array.from({ length: count }).map((_, index) => {
    const weekStartDate = addDays(currentMonday, -7 * index);
    const weekEndDate = addDays(weekStartDate, 6);

    const value = formatDate(weekStartDate);

    return {
      value,
      label: `Week: ${formatDisplayDate(value)} - ${formatDisplayDate(
        formatDate(weekEndDate)
      )}`,
    };
  });
}

function ReviewHoursPageContent() {
  const searchParams = useSearchParams();

  const workspace = searchParams.get("workspace") || "";
  const client = searchParams.get("client") || "";
  const project = searchParams.get("project") || "";

  const [user, setUser] = useState<StoredUser | null>(null);
  const [rows, setRows] = useState<ReviewHoursRow[]>([]);
  const [message, setMessage] = useState("");
  const [weekStart, setWeekStart] = useState(formatDate(getMonday(new Date())));
  const [selectedReviewer, setSelectedReviewer] =
    useState<ReviewHoursRow | null>(null);

  const [editRow, setEditRow] = useState<ReviewHoursRow | null>(null);
  const [editDate, setEditDate] = useState(weekStart);
  const [editHours, setEditHours] = useState("");
  const [editLogin, setEditLogin] = useState("");
  const [editLogout, setEditLogout] = useState("");
  const [editBreakMinutes, setEditBreakMinutes] = useState("0");
  const [editNotes, setEditNotes] = useState("");

  const weekOptions = buildWeekOptions(52);

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      setUser(JSON.parse(storedUser));
    }
  }, []);

  function loadRows() {
    if (!workspace || !client || !project) {
      setMessage("Missing workspace, client, or project.");
      return;
    }

    const query = new URLSearchParams({
      workspace,
      client,
      project,
      week_start: weekStart,
    });

    apiGet(`/api/timesheet/review-hours?${query.toString()}`)
      .then((response: any) => {
        setRows(response.rows || []);
        setMessage("");
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to load review hours.");
      });
  }

  useEffect(() => {
    loadRows();
  }, [workspace, client, project, weekStart]);

  function openEdit(row: ReviewHoursRow) {
    setEditRow(row);
    setEditDate(weekStart);
    setEditHours("");
    setEditLogin("");
    setEditLogout("");
    setEditBreakMinutes("0");
    setEditNotes("");
  }

  function saveManualEdit() {
    if (!editRow || !user) return;

    apiPost("/api/timesheet/review-hours/edit", {
      workspace,
      client_id: client,
      project_id: project,
      username: editRow.username,
      display_name: editRow.display_name || editRow.username,
      role: editRow.role || "",
      date: editDate,
      login: editLogin,
      logout: editLogout,
      break_minutes: Number(editBreakMinutes || 0),
      hours: Number(editHours || 0),
      notes: editNotes,
      edited_by: user.username,
    })
      .then(() => {
        setMessage("Review hours updated.");
        setEditRow(null);
        loadRows();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to save review hours edit.");
      });
  }

  return (
    <AppShell>
      <PageContainer>
        <PageHeader
          title="Review Hours"
          subtitle={`${prettyWorkspace(workspace)} • ${client || "Client"} • ${
            project ? project.replaceAll("_", " ") : "Project"
          }`}
        />

        {message && (
          <p className="mb-6 text-sm text-sky-400">
            {message}
          </p>
        )}

        <ContentCard title="Weekly Review Hours">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="min-w-[320px]">
              <label className="block text-sm text-slate-400 mb-2">
                Select Week
              </label>

              <select
                value={weekStart}
                onChange={(event) => {
                  setWeekStart(event.target.value);
                  setSelectedReviewer(null);
                  setEditRow(null);
                }}
                className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white outline-none focus:border-sky-500"
              >
                {weekOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-3">
              <Button onClick={loadRows}>
                Refresh
              </Button>
            </div>
          </div>

          <div className="overflow-auto rounded-xl border border-slate-800">
            <table className="w-full text-sm">
              <thead className="bg-slate-900 text-slate-400">
                <tr>
                  <th className="p-3 text-left">Reviewer Name</th>
                  <th className="p-3 text-right">Mon hrs</th>
                  <th className="p-3 text-right">Tues hrs</th>
                  <th className="p-3 text-right">Wed hrs</th>
                  <th className="p-3 text-right">Thurs hrs</th>
                  <th className="p-3 text-right">Fri hrs</th>
                  <th className="p-3 text-right">Sat hrs</th>
                  <th className="p-3 text-right">Sun hrs</th>
                  <th className="p-3 text-right">Week Total</th>
                  <th className="p-3 text-right">Actions</th>
                </tr>
              </thead>

              <tbody>
                {rows.map((row) => (
                  <tr
                    key={`${row.username}-${row.role}`}
                    className="border-t border-slate-800"
                  >
                    <td className="p-3 text-white">
                      <button
                        type="button"
                        onClick={() => setSelectedReviewer(row)}
                        className="text-left hover:text-sky-400"
                      >
                        <div>{row.display_name || row.username}</div>
                        <div className="text-xs text-slate-500">
                          {row.username} • {row.role || "—"}
                        </div>
                      </button>
                    </td>

                    <td className="p-3 text-right text-slate-300">
                      {Number(row.mon_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.tue_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.wed_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.thu_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.fri_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.sat_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right text-slate-300">
                      {Number(row.sun_hours || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right font-semibold text-white">
                      {Number(row.week_total || 0).toFixed(2)}
                    </td>
                    <td className="p-3 text-right">
                      <div className="flex justify-end gap-2">
                        <Button
                          variant="secondary"
                          onClick={() => setSelectedReviewer(row)}
                        >
                          Details
                        </Button>

                        <Button onClick={() => openEdit(row)}>
                          Edit
                        </Button>
                      </div>
                    </td>
                  </tr>
                ))}

                {rows.length === 0 && (
                  <tr>
                    <td
                      colSpan={10}
                      className="p-6 text-center text-slate-500"
                    >
                      No review hours found for this week.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ContentCard>

        {selectedReviewer && (
          <ContentCard
            title={`Details: ${
              selectedReviewer.display_name ||
              selectedReviewer.username
            }`}
          >
            <div className="flex justify-end mb-4">
              <Button
                variant="secondary"
                onClick={() => setSelectedReviewer(null)}
              >
                Close Details
              </Button>
            </div>

            <div className="overflow-auto rounded-xl border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th className="p-3 text-left">Date</th>
                    <th className="p-3 text-left">Login</th>
                    <th className="p-3 text-left">Logout</th>
                    <th className="p-3 text-right">Break</th>
                    <th className="p-3 text-right">Hours</th>
                    <th className="p-3 text-left">Source</th>
                    <th className="p-3 text-left">Notes</th>
                  </tr>
                </thead>

                <tbody>
                  {(selectedReviewer.details || []).map((item, index) => (
                    <tr
                      key={item.entry_id || index}
                      className="border-t border-slate-800"
                    >
                      <td className="p-3 text-slate-300">
                        {item.date || "—"}
                      </td>
                      <td className="p-3 text-slate-300">
                        {item.login || "—"}
                      </td>
                      <td className="p-3 text-slate-300">
                        {item.logout || "—"}
                      </td>
                      <td className="p-3 text-right text-slate-300">
                        {Number(item.break_minutes || 0)} min
                      </td>
                      <td className="p-3 text-right text-white">
                        {Number(item.hours || 0).toFixed(2)}
                      </td>
                      <td className="p-3 text-slate-300">
                        {item.source || "—"}
                      </td>
                      <td className="p-3 text-slate-300">
                        {item.notes || "—"}
                      </td>
                    </tr>
                  ))}

                  {(selectedReviewer.details || []).length === 0 && (
                    <tr>
                      <td
                        colSpan={7}
                        className="p-6 text-center text-slate-500"
                      >
                        No detailed entries found.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </ContentCard>
        )}

        {editRow && (
          <ContentCard
            title={`Edit Hours: ${editRow.display_name || editRow.username}`}
          >
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Date
                </label>
                <input
                  type="date"
                  value={editDate}
                  onChange={(event) => setEditDate(event.target.value)}
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Login
                </label>
                <input
                  value={editLogin}
                  onChange={(event) => setEditLogin(event.target.value)}
                  placeholder="08:30"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Logout
                </label>
                <input
                  value={editLogout}
                  onChange={(event) => setEditLogout(event.target.value)}
                  placeholder="17:00"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Break Minutes
                </label>
                <input
                  type="number"
                  value={editBreakMinutes}
                  onChange={(event) =>
                    setEditBreakMinutes(event.target.value)
                  }
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Hours
                </label>
                <input
                  type="number"
                  step="0.25"
                  value={editHours}
                  onChange={(event) => setEditHours(event.target.value)}
                  placeholder="7.50"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>

              <div>
                <label className="block text-xs text-slate-400 mb-1">
                  Notes
                </label>
                <input
                  value={editNotes}
                  onChange={(event) => setEditNotes(event.target.value)}
                  placeholder="Adjustment reason"
                  className="w-full rounded-xl border border-slate-700 bg-slate-950 px-4 py-3 text-sm text-white"
                />
              </div>
            </div>

            <div className="flex justify-end gap-3">
              <Button
                variant="secondary"
                onClick={() => setEditRow(null)}
              >
                Cancel
              </Button>

              <Button onClick={saveManualEdit}>
                Save Edit
              </Button>
            </div>
          </ContentCard>
        )}
      </PageContainer>
    </AppShell>
  );
}

export default function ReviewHoursPage() {
  return (
    <Suspense fallback={<div>Loading review hours...</div>}>
      <ReviewHoursPageContent />
    </Suspense>
  );
}