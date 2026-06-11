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

function formatMMDDYYYY(dateString: string) {
  const date = new Date(`${dateString}T00:00:00`);

  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  const yyyy = String(date.getFullYear());

  return `${mm}${dd}${yyyy}`;
}

function formatTimeDisplay(value?: string) {
  if (!value) return "—";

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return date.toLocaleTimeString("en-US", {
    hour: "numeric",
    minute: "2-digit",
  });
}

function getWeekDays(weekStart: string) {
  const monday = new Date(`${weekStart}T00:00:00`);

  return [
    { key: "mon", label: "Mon", field: "mon_hours", date: formatDate(monday) },
    { key: "tue", label: "Tues", field: "tue_hours", date: formatDate(addDays(monday, 1)) },
    { key: "wed", label: "Wed", field: "wed_hours", date: formatDate(addDays(monday, 2)) },
    { key: "thu", label: "Thurs", field: "thu_hours", date: formatDate(addDays(monday, 3)) },
    { key: "fri", label: "Fri", field: "fri_hours", date: formatDate(addDays(monday, 4)) },
    { key: "sat", label: "Sat", field: "sat_hours", date: formatDate(addDays(monday, 5)) },
    { key: "sun", label: "Sun", field: "sun_hours", date: formatDate(addDays(monday, 6)) },
  ];
}

function getDayHours(row: ReviewHoursRow, field: string) {
  return Number((row as any)[field] || 0);
}

function getDayDetails(row: ReviewHoursRow, date: string) {
  return (row.details || []).filter((item) => item.date === date);
}

function getTodayDateString() {
  return formatDate(new Date());
}

function isQcAndUp(role?: string) {
  return [
    "QC",
    "TL",
    "RM",
    "INSYT Admin",
    "CDS Admin",
  ].includes(role || "");
}

function getEntryTimestamp(item: TimeEntryDetail) {
  const value = item.logout || item.login;

  if (!value) return 0;

  const parsed = new Date(value).getTime();

  if (!Number.isNaN(parsed)) return parsed;

  if (item.date && value) {
    const parsedWithDate = new Date(`${item.date}T${value}`).getTime();

    if (!Number.isNaN(parsedWithDate)) return parsedWithDate;
  }

  return 0;
}


function getDayTotal(row: ReviewHoursRow, date: string, field: string) {
  const detailTotal = getDayDetails(row, date).reduce(
    (total, item) => total + Number(item.hours || 0),
    0
  );

  if (detailTotal > 0) return detailTotal;

  return getDayHours(row, field);
}

function getLatestLogin(row: ReviewHoursRow, date: string) {
  const details = getDayDetails(row, date).filter((item) => item.login);
  return details[details.length - 1]?.login || "";
}

function getLatestLogout(row: ReviewHoursRow, date: string) {
  const details = getDayDetails(row, date).filter((item) => item.logout);
  return details[details.length - 1]?.logout || "";
}

function getDayLoginLogoutPairs(row: ReviewHoursRow, date: string) {
  const details = getDayDetails(row, date)
    .filter((item) => item.login || item.logout)
    .sort((a, b) => getEntryTimestamp(a) - getEntryTimestamp(b));

  if (details.length === 0) return "—";

  const pairs = details.map((item) => {
    const login = item.login ? formatTimeDisplay(item.login) : "—";
    const logout = item.logout ? formatTimeDisplay(item.logout) : "—";

    return `${login} - ${logout}`;
  });

  return pairs.join("; ");
}

function isReviewerLoggedInForDate(row: ReviewHoursRow, date: string) {
  const details = getDayDetails(row, date)
    .filter((item) => item.login || item.logout)
    .sort((a, b) => getEntryTimestamp(a) - getEntryTimestamp(b));

  if (details.length === 0) return false;

  const latest = details[details.length - 1];

  return Boolean(latest.login && !latest.logout);
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
  const [activeTab, setActiveTab] = useState("weekly");
  const [unlockedDates, setUnlockedDates] = useState<Record<string, boolean>>({});
  const [selectedReviewer, setSelectedReviewer] = useState<ReviewHoursRow | null>(null);

  const [editRow, setEditRow] = useState<ReviewHoursRow | null>(null);
  const [editDate, setEditDate] = useState(weekStart);
  const [editHours, setEditHours] = useState("");
  const [editLogin, setEditLogin] = useState("");
  const [editLogout, setEditLogout] = useState("");
  const [editBreakMinutes, setEditBreakMinutes] = useState("0");
  const [editNotes, setEditNotes] = useState("");

  const weekOptions = buildWeekOptions(52);
  const weekDays = getWeekDays(weekStart);
  const activeDay = weekDays.find((day) => day.key === activeTab);

  const todayDate = getTodayDateString();
  const canUnlockDates = isQcAndUp(user?.role);

  const activeDayIsToday =
    Boolean(activeDay) && activeDay?.date === todayDate;

  const activeDayIsUnlocked =
    Boolean(activeDay) &&
    (
      activeDayIsToday ||
      Boolean(unlockedDates[activeDay!.date])
    );

  useEffect(() => {
    const storedUser = localStorage.getItem("insyt_user");

    if (storedUser) {
      const parsedUser = JSON.parse(storedUser);
      setUser(parsedUser);

      localStorage.setItem(
        "insyt_review_hours_context",
        JSON.stringify({
          workspace,
          client_id: client,
          project_id: project,
          username: parsedUser.username,
          display_name: parsedUser.display_name || parsedUser.username,
          role: parsedUser.role || "1L",
        })
      );
    }
  }, [workspace, client, project]);

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

  function logInForDay(date: string) {
    if (!user) return;

    localStorage.setItem(
      "insyt_review_hours_context",
      JSON.stringify({
        workspace,
        client_id: client,
        project_id: project,
        username: user.username,
        display_name: user.display_name || user.username,
        role: user.role || "1L",
        date,
      })
    );

    apiPost("/api/timesheet/review-hours/login", {
      workspace,
      client_id: client,
      project_id: project,
      username: user.username,
      display_name: user.display_name || user.username,
      role: user.role || "1L",
      date,
    })
      .then(() => {
        setMessage("Logged in.");
        loadRows();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to log in.");
      });
  }

  function logOutForDay(date: string) {
    if (!user) return;

    apiPost("/api/timesheet/review-hours/logout", {
      workspace,
      client_id: client,
      project_id: project,
      username: user.username,
      display_name: user.display_name || user.username,
      role: user.role || "1L",
      date,
    })
      .then(() => {
        setMessage("Logged out.");
        loadRows();
      })
      .catch((error) => {
        console.error(error);
        setMessage("Failed to log out.");
      });
  }

  function toggleDateLock(date: string) {
    if (!canUnlockDates) return;

    setUnlockedDates((current) => ({
      ...current,
      [date]: !current[date],
    }));
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

        <ContentCard title="Review Hours">
          <div className="flex flex-wrap items-center justify-between gap-4 mb-6">
            <div className="min-w-[320px]">
              <label className="block text-sm text-slate-400 mb-2">
                Select Week
              </label>

              <select
                value={weekStart}
                onChange={(event) => {
                  setWeekStart(event.target.value);
                  setActiveTab("weekly");
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

          <div className="mb-6 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setActiveTab("weekly")}
              className={
                activeTab === "weekly"
                  ? "rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white"
                  : "rounded-xl border border-slate-800 bg-slate-950 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
              }
            >
              Weekly Totals
            </button>

            {weekDays.map((day) => (
              <button
                key={day.key}
                type="button"
                onClick={() => setActiveTab(day.key)}
                className={
                  activeTab === day.key
                    ? "rounded-xl bg-teal-600 px-4 py-2 text-sm font-semibold text-white"
                    : "rounded-xl border border-slate-800 bg-slate-950 px-4 py-2 text-sm text-slate-300 hover:bg-slate-800"
                }
              >
                {day.label} {formatMMDDYYYY(day.date)}
              </button>
            ))}
          </div>

          {activeTab === "weekly" && (
            <div className="overflow-auto rounded-xl border border-slate-800">
              <table className="w-full text-sm">
                <thead className="bg-slate-900 text-slate-400">
                  <tr>
                    <th className="p-3 text-left">Reviewer Name</th>
                    <th className="p-3 text-left">Current</th>

                    {weekDays.map((day) => (
                      <th key={day.key} className="p-3 text-right">
                        {day.label}
                      </th>
                    ))}

                    <th className="p-3 text-right">Week Total</th>
                  </tr>
                </thead>

                <tbody>
                  {rows.map((row) => (
                    <tr
                      key={`${row.username}-${row.role}`}
                      className="border-t border-slate-800"
                    >
                      <td className="p-3 text-white">
                        <div>{row.display_name || row.username}</div>
                        <div className="text-xs text-slate-500">
                          {row.username} • {row.role || "—"}
                        </div>
                      </td>

                      <td className="p-3">
                        {isReviewerLoggedInForDate(row, todayDate) ? (
                          <span className="rounded-full bg-lime-500/10 px-3 py-1 text-xs font-semibold text-lime-300">
                            Logged In
                          </span>
                        ) : (
                          <span className="rounded-full bg-slate-800 px-3 py-1 text-xs font-semibold text-slate-400">
                            Logged Out
                          </span>
                        )}
                      </td>

                      {weekDays.map((day) => (
                        <td
                          key={day.key}
                          className="p-3 text-right text-slate-300"
                        >
                          {getDayTotal(row, day.date, day.field).toFixed(2)}
                        </td>
                      ))}

                      <td className="p-3 text-right font-semibold text-white">
                        {Number(row.week_total || 0).toFixed(2)}
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
          )}

          {activeDay && (
            <>
              <div className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-xl border border-slate-800 bg-slate-950 p-4">
                <div>
                  <div className="text-sm font-semibold text-white">
                    {activeDay.label} {formatMMDDYYYY(activeDay.date)}
                  </div>

                  <div className="mt-1 text-xs text-slate-400">
                    {activeDayIsUnlocked
                      ? activeDayIsToday
                        ? "Unlocked automatically because this date is today."
                        : "Unlocked by authorized QC/leadership for corrections."
                      : "Locked because this date is not today."}
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <span
                    className={
                      activeDayIsUnlocked
                        ? "rounded-full bg-lime-500/10 px-3 py-1 text-xs font-semibold text-lime-300"
                        : "rounded-full bg-amber-500/10 px-3 py-1 text-xs font-semibold text-amber-300"
                    }
                  >
                    {activeDayIsUnlocked ? "Unlocked" : "Locked"}
                  </span>

                  {!activeDayIsToday && canUnlockDates && (
                    <Button
                      variant="secondary"
                      onClick={() => toggleDateLock(activeDay.date)}
                    >
                      {unlockedDates[activeDay.date]
                        ? "Lock Date"
                        : "Unlock Date"}
                    </Button>
                  )}
                </div>
              </div>

              <div className="overflow-auto rounded-xl border border-slate-800">
                <table className="w-full text-sm">
                  <thead className="bg-slate-900 text-slate-400">
                    <tr>
                      <th className="p-3 text-left">Reviewer Name</th>
                      <th className="p-3 text-left">Status</th>
                      <th className="p-3 text-left">First Login</th>
                      <th className="p-3 text-left">Last Logout</th>
                      <th className="p-3 text-left">Login / Logout History</th>
                      <th className="p-3 text-right">Day Total</th>
                      <th className="p-3 text-right">Action</th>
                    </tr>
                  </thead>

                  <tbody>
                    {rows.map((row) => {
                      const isCurrentUser =
                        row.username === user?.username;

                      const isLoggedIn = isReviewerLoggedInForDate(
                        row,
                        activeDay.date
                      );

                      return (
                        <tr
                          key={`${activeDay.date}-${row.username}`}
                          className="border-t border-slate-800"
                        >
                          <td className="p-3 text-white">
                            <div>{row.display_name || row.username}</div>
                            <div className="text-xs text-slate-500">
                              {row.username} • {row.role || "—"}
                            </div>
                          </td>

                          <td className="p-3 text-slate-300">
                            {isLoggedIn ? (
                              <span className="text-lime-300">
                                Logged In
                              </span>
                            ) : (
                              <span className="text-slate-400">
                                Logged Out
                              </span>
                            )}
                          </td>

                          <td className="p-3 text-slate-300">
                            {formatTimeDisplay(
                              getLatestLogin(row, activeDay.date)
                            )}
                          </td>

                          <td className="p-3 text-slate-300">
                            {formatTimeDisplay(
                              getLatestLogout(row, activeDay.date)
                            )}
                          </td>

                          <td className="p-3 text-slate-300 whitespace-nowrap">
                            {getDayLoginLogoutPairs(row, activeDay.date)}
                          </td>

                          <td className="p-3 text-right font-semibold text-white">
                            {getDayTotal(
                              row,
                              activeDay.date,
                              activeDay.field
                            ).toFixed(2)}
                          </td>

                          <td className="p-3 text-right">
                            {isCurrentUser ? (
                              activeDayIsUnlocked ? (
                                isLoggedIn ? (
                                  <Button
                                    variant="secondary"
                                    onClick={() =>
                                      logOutForDay(activeDay.date)
                                    }
                                  >
                                    Log Out
                                  </Button>
                                ) : (
                                  <Button
                                    onClick={() =>
                                      logInForDay(activeDay.date)
                                    }
                                  >
                                    Log In
                                  </Button>
                                )
                              ) : (
                                <span className="text-amber-300 text-xs font-semibold">
                                  Locked
                                </span>
                              )
                            ) : canUnlockDates && activeDayIsUnlocked ? (
                              <Button
                                variant="secondary"
                                onClick={() => {
                                  setEditRow(row);
                                  setEditDate(activeDay.date);
                                  setEditHours("");
                                  setEditLogin("");
                                  setEditLogout("");
                                  setEditBreakMinutes("0");
                                  setEditNotes("");
                                }}
                              >
                                Edit
                              </Button>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}

                    {rows.length === 0 && (
                      <tr>
                        <td
                          colSpan={7}
                          className="p-6 text-center text-slate-500"
                        >
                          No reviewers found for this day.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </>
          )}
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