import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import AuthGuard from "./AuthGuard";
import SessionTimeout from "./SessionTimeout";

export default function AppShell({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <AuthGuard>
      <SessionTimeout />

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