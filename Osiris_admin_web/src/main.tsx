import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./index.css";
import App from "./App.tsx";
import ErrorBoundary from "./components/ErrorBoundary";
import { API_CONFIG_ERROR } from "./api/client";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    {/* Outermost: a render error in the sidebar or the login screen shows a reload prompt, not a blank tab. */}
    <ErrorBoundary>
      {API_CONFIG_ERROR ? (
        <div className="error-message" role="alert" style={{ margin: 40 }}>
          {API_CONFIG_ERROR}
        </div>
      ) : (
        <App />
      )}
    </ErrorBoundary>
  </StrictMode>
);
