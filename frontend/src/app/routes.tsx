import { Navigate, Route, Routes } from "react-router";

import { CapturePage } from "../pages/capture-page";
import { ObservationDetailPage } from "../pages/observation-detail-page";
import { ObservationReviewPage } from "../pages/observation-review-page";
import { TodayMediaPage } from "../pages/today-media-page";

export function AppRoutes() {
  return (
    <Routes>
      <Route index element={<TodayMediaPage />} />
      <Route path="capture" element={<CapturePage />} />
      <Route
        path="observations/:observationId/review"
        element={<ObservationReviewPage />}
      />
      <Route path="observations/:observationId" element={<ObservationDetailPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
