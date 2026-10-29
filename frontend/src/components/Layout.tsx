import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `px-3 py-2 text-sm transition-colors ${
    isActive ? "text-ink-700 font-semibold" : "text-ink-500 hover:text-ink-700"
  }`;

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-100/80 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-6 px-6 py-5">
          <Link to="/" className="block">
            <p className="font-display text-2xl font-semibold tracking-tight text-ink-700">
              StarBegonia
            </p>
            <p className="mt-0.5 text-sm text-ink-400">家庭收支</p>
          </Link>
          <nav className="flex flex-wrap items-center gap-1">
            <NavLink to="/" end className={linkClass}>
              概览
            </NavLink>
            <NavLink to="/bills" className={linkClass}>
              流水
            </NavLink>
            <NavLink to="/categories" className={linkClass}>
              分类
            </NavLink>
            <NavLink to="/bills/new" className={linkClass}>
              记账
            </NavLink>
          </nav>
          <div className="flex items-center gap-3 text-sm">
            <Link
              to="/account"
              className="rounded-md px-2 py-1 text-ink-600 hover:bg-ink-50 hover:text-ink-800"
            >
              {user?.person?.display_name}
            </Link>
            <button
              type="button"
              onClick={logout}
              className="rounded-md px-2 py-1 text-ink-500 hover:bg-ink-50 hover:text-ink-700"
            >
              退出
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-10 animate-[fadeIn_0.35s_ease]">
        <Outlet />
      </main>
    </div>
  );
}
