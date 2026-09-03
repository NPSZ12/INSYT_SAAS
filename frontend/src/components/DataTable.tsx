import React from "react";

import Button from "./Button";

type Column = {
  key: string;
  label: string;
};

type DataTableRow = Record<string, React.ReactNode>;

type DataTableProps = {
  columns: Column[];
  data: DataTableRow[];
  showActions?: boolean;
  className?: string;
  emptyMessage?: string;
};

export default function DataTable({
  columns,
  data,
  showActions = false,
  className = "",
  emptyMessage = "No records found.",
}: DataTableProps) {
  return (
    <div className={`insyt-table-shell ${className}`}>
      <div className="overflow-x-auto">
        <table className="insyt-table">
          <thead className="insyt-table-header">
            <tr>
              {columns.map((column) => (
                <th
                  key={column.key}
                  className="insyt-table-header-cell text-xs uppercase tracking-wide"
                >
                  {column.label}
                </th>
              ))}

              {showActions && (
                <th className="insyt-table-header-cell text-right text-xs uppercase tracking-wide">
                  Action
                </th>
              )}
            </tr>
          </thead>

          <tbody>
            {data.length === 0 ? (
              <tr>
                <td
                  colSpan={columns.length + (showActions ? 1 : 0)}
                  className="insyt-table-cell py-8 text-center insyt-text-muted"
                >
                  {emptyMessage}
                </td>
              </tr>
            ) : (
              data.map((row, rowIndex) => (
                <tr
                  key={rowIndex}
                  className="insyt-table-row"
                >
                  {columns.map((column) => (
                    <td
                      key={column.key}
                      className="insyt-table-cell align-top"
                    >
                      {row[column.key]}
                    </td>
                  ))}

                  {showActions && (
                    <td className="insyt-table-cell text-right align-top">
                      <Button variant="secondary">
                        Edit
                      </Button>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}