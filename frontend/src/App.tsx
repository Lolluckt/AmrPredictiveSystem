import { Navigate, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { me } from "@/api/endpoints";
import { useAuthStore } from "@/store/auth";
import { Layout } from "@/components/Layout";
import { RequireAuth, RequireRole } from "@/components/RequireRole";
import { LiveChannelHost } from "@/components/LiveChannelHost";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Robots from "@/pages/Robots";
import RobotDetail from "@/pages/RobotDetail";
import Predictive from "@/pages/Predictive";
import Analytics from "@/pages/Analytics";
import Alerts from "@/pages/Alerts";
import Tickets from "@/pages/Tickets";
import Missions from "@/pages/Missions";
import Users from "@/pages/Users";

export default function App() {
  const { accessToken, setUser, user } = useAuthStore();
  const profile = useQuery({
    queryKey: ["me"],
    queryFn: me,
    enabled: !!accessToken && !user,
    retry: false,
  });

  useEffect(() => {
    if (profile.data) setUser(profile.data);
  }, [profile.data, setUser]);

  return (
    <>
      {accessToken && <LiveChannelHost />}
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard"    element={<Dashboard />} />
          <Route path="/robots"       element={<Robots />} />
          <Route path="/robots/:id"   element={<RobotDetail />} />
          <Route path="/predictive"   element={<RequireRole roles={["admin","engineer"]}><Predictive /></RequireRole>} />
          <Route path="/analytics"    element={<RequireRole roles={["admin","engineer"]}><Analytics /></RequireRole>} />
          <Route path="/alerts"       element={<Alerts />} />
          <Route path="/tickets"      element={<Tickets />} />
          <Route path="/missions"     element={<Missions />} />
          <Route path="/admin/users"  element={<RequireRole roles={["admin"]}><Users /></RequireRole>} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </>
  );
}
