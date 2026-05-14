import Button from "./Button";

type Column = {
  key: string;
  label: string;
};

type DataTableProps = {
  columns: Column[];
  data: Record<string, string>[];
  showActions?: boolean;
};

export default function DataTable({
  columns,
  data,
  showActions = false,
}: DataTableProps) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
      <table className="w-full">
        <thead className="bg-slate-950 text-slate-400 text-left">
          <tr>
            {columns.map((column) => (
              <th key={column.key} className="p-5">
                {column.label}
              </th>
            ))}

            {showActions && (
              <th className="p-5 text-right">
                Action
              </th>
            )}
          </tr>
        </thead>

        <tbody>
          {data.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-t border-slate-800">
              {columns.map((column) => (
                <td key={column.key} className="p-5 text-white">
                  {row[column.key]}
                </td>
              ))}

              {showActions && (
                <td className="p-5 text-right">
                  <Button variant="secondary">
                    Edit
                  </Button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}