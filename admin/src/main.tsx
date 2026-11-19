import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ApiError } from "@/services/ApiError";
import { AuthProvider } from "@/app/AuthContext";
import App from "@/App";

// Material Symbols icon font is loaded by @font-face in
// styles/theme.css (subset of used ligatures — scripts/subset-icons.mjs).
import "@/styles/theme.css";
import "@/styles/ui.css";
import "@/styles/layout.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Auth/permission failures are terminal — retrying only duplicates the
      // refresh call. Everything else keeps the single retry.
      retry: (failureCount, error) =>
        failureCount < 1 &&
        !(
          error instanceof ApiError &&
          (error.status === 401 || error.status === 403)
        ),
      refetchOnWindowFocus: false,
      staleTime: 10_000,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <App />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
