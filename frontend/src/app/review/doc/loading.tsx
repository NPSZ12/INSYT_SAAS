export default function LoadingReviewDoc() {
  return (
    <main className="min-h-screen bg-slate-950 text-white flex items-center justify-center">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8 w-full max-w-md text-center">
        <div className="mx-auto mb-6 h-12 w-12 rounded-full border-4 border-slate-700 border-t-teal-500 animate-spin" />

        <h1 className="text-2xl font-bold mb-2">
          Loading Review Workspace
        </h1>

        <p className="text-slate-400">
          Preparing document text, native viewer, protocol fields, and linked entities.
        </p>
      </div>
    </main>
  );
}