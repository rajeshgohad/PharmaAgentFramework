import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import "./index.css";
import Layout from "./components/Layout";
import Catalog from "./pages/Catalog";
import AgentPage from "./pages/AgentPage";
import Orchestrator from "./pages/Orchestrator";
import Dashboards from "./pages/Dashboards";
import Toolkit from "./pages/Toolkit";
import Tables from "./pages/Tables";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/catalog" replace />} />
          <Route path="catalog" element={<Catalog />} />
          <Route path="agent/:id" element={<AgentPage />} />
          <Route path="orchestrator" element={<Orchestrator />} />
          <Route path="dashboards" element={<Dashboards />} />
          <Route path="toolkit" element={<Toolkit />} />
          <Route path="tables" element={<Tables />} />
        </Route>
      </Routes>
    </BrowserRouter>
  </React.StrictMode>
);
