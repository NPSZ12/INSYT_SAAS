export type ReviewWorkspace = "capture" | "discovery";

export function getWorkspaceReviewConfig(workspace: ReviewWorkspace) {
  const base = `/api/${workspace}`;
  const pageBase = `/${workspace}`;

  return {
    workspace,

    api: {
      currentDocument: `${base}/review/current`,
      files: `${base}/files`,
      detectionHits:
        `${base}/processing-center/data-element-detection/document-hits`,
      projectProtocol: (projectId: string) =>
        `${base}/projects/${encodeURIComponent(projectId)}/protocol`,

      codingMap: "/api/review/coding-map",
    },

    pages: {
      reviewDocument: `${pageBase}/review/doc`,
      batchManagement: `${pageBase}/batch-management`,
      capturedEntities: `${pageBase}/captured-entities`,
      finalEntityViewer: `${pageBase}/entities/final-viewer`,
    },
  };
}
