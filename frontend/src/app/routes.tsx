import { Navigate, Route, Routes } from "react-router";

import { RequireAuth } from "../features/auth/auth-context";
import { AccountPage } from "../pages/account-page";
import { CapturePage } from "../pages/capture-page";
import { ChildProfilePage } from "../pages/child-profile-page";
import { ChildrenManagePage } from "../pages/children-manage-page";
import { ExportHistoryPage } from "../pages/export-history-page";
import { KindergartenPage } from "../pages/kindergarten-page";
import { LoginPage } from "../pages/login-page";
import { MinePage } from "../pages/mine-page";
import { MonthMediaPage } from "../pages/month-media-page";
import { ObservationDetailPage } from "../pages/observation-detail-page";
import { ObservationReviewPage } from "../pages/observation-review-page";
import { SettingsPage } from "../pages/settings-page";
import { TodayMediaPage } from "../pages/today-media-page";

export function AppRoutes() {
  return (
    <Routes>
      {/* 登录页本身不能被登录闸门挡住 */}
      <Route element={<LoginPage />} path="login" />

      <Route element={<Guarded><TodayMediaPage /></Guarded>} index />
      <Route element={<Guarded><CapturePage /></Guarded>} path="capture" />
      <Route element={<Guarded><MonthMediaPage /></Guarded>} path="month" />
      <Route element={<Guarded><MinePage /></Guarded>} path="mine" />
      <Route
        element={<Guarded><ObservationReviewPage /></Guarded>}
        path="observations/:observationId/review"
      />
      <Route
        element={<Guarded><ObservationDetailPage /></Guarded>}
        path="observations/:observationId"
      />
      <Route element={<Guarded><SettingsPage /></Guarded>} path="settings" />

      {/* 以下页面在 src/config/features.ts 对应开关为 false 时会自行跳回 /mine，
          所以路由可以先注册，不会出现走不通的入口 */}
      <Route element={<Guarded><AccountPage /></Guarded>} path="account" />
      <Route element={<Guarded><KindergartenPage /></Guarded>} path="kindergarten" />
      <Route element={<Guarded><ExportHistoryPage /></Guarded>} path="exports" />
      <Route element={<Guarded><ChildrenManagePage /></Guarded>} path="children" />
      <Route element={<Guarded><ChildProfilePage /></Guarded>} path="children/:childId" />

      <Route element={<Navigate replace to="/" />} path="*" />
    </Routes>
  );
}

function Guarded({ children }: { children: React.ReactNode }) {
  return <RequireAuth>{children}</RequireAuth>;
}
