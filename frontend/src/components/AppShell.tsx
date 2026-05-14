import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import AuthGuard from "./AuthGuard";

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <main className="min-h-screen bg-slate-950 text-white flex">
        <Sidebar />

        <section className="flex-1 min-h-screen">
          <Topbar />
          {children}
        </section>
      </main>
    </AuthGuard>
  );
}