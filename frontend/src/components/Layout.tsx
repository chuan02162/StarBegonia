import { Link, NavLink, Outlet } from "react-router-dom";
import { useAuth } from "../auth/AuthContext";

const linkClass = ({ isActive }: { isActive: boolean }) =>
  `shrink-0 rounded-md px-3 py-2 text-sm transition-colors ${
    isActive ? "bg-ink-50 font-semibold text-ink-700" : "text-ink-500 hover:text-ink-700"
  }`;

export function Layout() {
  const { user, logout } = useAuth();

  return (
    <div className="min-h-screen">
      <header className="border-b border-ink-100/80 bg-white/70 backdrop-blur-sm">
        <div className="mx-auto flex max-w-5xl flex-col gap-3 px-4 py-4 sm:px-6 sm:py-5 md:gap-4">
          <div className="flex items-center justify-between gap-3">
            <Link to="/" className="min-w-0">
              <p className="font-display text-xl font-semibold tracking-tight text-ink-700 sm:text-2xl">
                StarBegonia
              </p>
              <p className="mt-0.5 text-xs text-ink-400 sm:text-sm">家庭收支</p>
            </Link>
            <div className="flex shrink-0 items-center gap-1 text-sm sm:gap-2">
              <Link
                to="/account"
                className="max-w-[9rem] truncate rounded-md px-2 py-1.5 text-ink-600 hover:bg-ink-50 hover:text-ink-800 sm:max-w-none"
              >
                {user?.person?.display_name}
              </Link>
              <button
                type="button"
                onClick={logout}
                className="rounded-md px-2 py-1.5 text-ink-500 hover:bg-ink-50 hover:text-ink-700"
              >
                退出
              </button>
            </div>
          </div>

          <nav
            className="-mx-4 flex gap-0.5 overflow-x-auto border-t border-ink-100/80 px-4 pt-3 scrollbar-none sm:-mx-0 sm:border-t-0 sm:px-0 sm:pt-0 md:flex-wrap"
            aria-label="主导航"
          >
            <NavLink to="/" end className={linkClass}>
              概览
            </NavLink>
            <NavLink to="/bills" className={linkClass}>
              流水
            </NavLink>
            <NavLink to="/categories" className={linkClass}>
              分类
            </NavLink>
            <NavLink to="/settlements" className={linkClass}>
              结算
            </NavLink>
            <NavLink to="/bills/new" className={linkClass}>
              记账
            </NavLink>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-8 sm:px-6 sm:py-10 animate-[fadeIn_0.35s_ease]">
        <Outlet />
      </main>
    </div>
  );
}
