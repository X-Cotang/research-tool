import { type RouteConfig, index, route, layout } from "@react-router/dev/routes";

export default [
  route("login", "routes/login.tsx"),
  layout("routes/layout.tsx", [
    index("routes/dashboard.tsx"),
    route("projects", "routes/projects.tsx"),
    route("projects/:id", "routes/project-detail.tsx"),
    route("jobs/:id", "routes/job-session.tsx"),
    route("chat", "routes/chat.tsx"),
    route("chat/:id", "routes/chat-detail.tsx"),
    route("runs", "routes/runs.tsx"),
    route("runs/:id", "routes/run-detail.tsx"),
    route("skills", "routes/skills.tsx"),
    route("prompts", "routes/prompts.tsx"),
    route("findings", "routes/findings.tsx"),
    route("agent", "routes/agent.tsx"),
    route("settings", "routes/settings.tsx"),
  ]),
] satisfies RouteConfig;
