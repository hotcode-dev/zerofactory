import { ZeroFactoryKanbanApp } from "./App.jsx";

if (typeof window !== "undefined" && window.__HERMES_PLUGINS__) {
  window.__HERMES_PLUGINS__.register("zerofactory", ZeroFactoryKanbanApp);
}

export { ZeroFactoryKanbanApp };
