import { Navigate, Outlet } from "react-router-dom";
import { CircularProgress, Box } from "@mui/material";
import { useAuth } from "../contexts/AuthContext";

interface ProtectedRouteProps {
  requiredRole?: string;
}

const ROLE_ORDER: Record<string, number> = {
  VIEWER: 0, TESTER: 1, LEAD: 2, ADMIN: 3,
};

export default function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { user, isLoading } = useAuth();

  if (isLoading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", alignItems: "center", height: "100vh" }}>
        <CircularProgress />
      </Box>
    );
  }

  if (!user) return <Navigate to="/login" replace />;

  if (requiredRole && ROLE_ORDER[user.role] < ROLE_ORDER[requiredRole]) {
    return <Navigate to="/403" replace />;
  }

  return <Outlet />;
}
