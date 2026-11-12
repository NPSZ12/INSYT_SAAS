/**
 * INSYT workbook document families.
 *
 * Parent Excel workbooks remain independently navigable.
 * Derived numbered CSV worksheets retain their original Doc IDs
 * but are excluded from the top-level Files population.
 *
 * A CSV is hidden only when its exact Excel parent exists.
 * Standalone CSVs and unrelated files remain visible.
 */

export type WorkbookFamilyFile = {
  doc_id: string;
  file_name: string;
  extension: string;
  blob_path: string;
};

export type WorkbookFamily<T extends WorkbookFamilyFile> = {
  parent: T;
  worksheets: T[];
};

const EXCEL_EXTENSIONS = new Set(["xls", "xlsx", "xlsm"]);

function extensionOf(file: WorkbookFamilyFile): string {
  return String(
    file.extension ||
      file.file_name?.split(".").pop() ||
      ""
  ).replace(/^\./, "").toLowerCase();
}

function documentId(file: WorkbookFamilyFile): string {
  return String(file.doc_id || "").trim();
}

function worksheetIdentity(
  file: WorkbookFamilyFile
): { parentId: string; index: number } | null {
  if (extensionOf(file) !== "csv") return null;

  const match = /^(.+)\.([1-9]\d*)$/.exec(documentId(file));
  if (!match) return null;

  return {
    parentId: match[1],
    index: Number(match[2]),
  };
}

export function groupWorkbookFamilies<
  T extends WorkbookFamilyFile
>(files: T[]): {
  parents: T[];
  families: Map<string, WorkbookFamily<T>>;
} {
  const excelParents = new Map<string, T>();

  for (const file of files) {
    if (EXCEL_EXTENSIONS.has(extensionOf(file))) {
      const id = documentId(file);
      if (id) excelParents.set(id, file);
    }
  }

  const families = new Map<string, WorkbookFamily<T>>();

  for (const [id, parent] of excelParents) {
    families.set(id, { parent, worksheets: [] });
  }

  const parents: T[] = [];

  for (const file of files) {
    const child = worksheetIdentity(file);
    const family = child
      ? families.get(child.parentId)
      : undefined;

    if (family) {
      family.worksheets.push(file);
    } else {
      parents.push(file);
    }
  }

  for (const family of families.values()) {
    family.worksheets.sort((a, b) => {
      const ai = worksheetIdentity(a)?.index ?? 0;
      const bi = worksheetIdentity(b)?.index ?? 0;
      return ai - bi;
    });
  }

  return { parents, families };
}
