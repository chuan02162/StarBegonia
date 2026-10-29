import type { ReactNode } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { AccountPage } from "./pages/AccountPage";
import { BillDetailPage } from "./pages/BillDetailPage";
import { BillsPage } from "./pages/BillsPage";
import { BootstrapPage } from "./pages/BootstrapPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { LoginPage } from "./pages/LoginPage";
import { NewBillPage } from "./pages/NewBillPage";
import { OverviewPage } from "./pages/OverviewPage";
import { RegisterPage } from "./pages/RegisterPage";
import { SourceCredentialPage } from "./pages/SourceCredentialPage";

function Protected({ children }: { children: ReactNode }) {
  const { user, loading, needsBootstrap } = useAuth();
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center text-ink-500">加载中…</div>
    );
  }
  if (needsBootstrap) return <Navigate to="/bootstrap" replace />;
  if (!user) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/bootstrap" element={<BootstrapPage />} />
      <Route
        path="/"
        element={
          <Protected>
            <Layout />
          </Protected>
        }
      >
        <Route index element={<OverviewPage />} />
        <Route path="bills" element={<BillsPage />} />
        <Route path="bills/new" element={<NewBillPage />} />
        <Route path="bills/:billId" element={<BillDetailPage />} />
        <Route path="categories" element={<CategoriesPage />} />
        <Route path="account" element={<AccountPage />} />
        <Route path="account/sources/:sourceType" element={<SourceCredentialPage />} />
        <Route path="people" element={<Navigate to="/account" replace />} />
        <Route path="invites" element={<Navigate to="/account" replace />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
