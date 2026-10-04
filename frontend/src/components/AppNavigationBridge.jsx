import { useEffect } from "react";
import { useNavigate } from "react-router-dom";

import { registerAppNavigation } from "@/lib/appNavigation";

export default function AppNavigationBridge() {
  const navigate = useNavigate();

  useEffect(() => registerAppNavigation(navigate), [navigate]);
  return null;
}
