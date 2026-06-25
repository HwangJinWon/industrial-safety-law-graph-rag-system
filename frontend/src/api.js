export function getApiBaseUrl() {
  return import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000";
}

async function request(path, options = {}) {
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  const contentType = response.headers.get("content-type") || "";
  const data = contentType.includes("application/json")
    ? await response.json()
    : await response.text();

  if (!response.ok) {
    const message = typeof data === "string" ? data : data.detail || "API request failed";
    throw new Error(message);
  }

  return data;
}

function post(path, body) {
  return request(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

export function fetchHealth() {
  return request("/health");
}

export function generateChecklist(payload) {
  return post("/site-checklist-ui", payload);
}

export function askChat(payload) {
  return post("/ask", payload);
}

export function fetchLawDetail(nodeId) {
  return request(`/law/${encodeURIComponent(nodeId)}`);
}

export function listProjects() {
  return request("/projects");
}

export function createProject(project) {
  return post("/projects", project);
}

export function listChecklistHistory() {
  return request("/history/checklists");
}

export function saveChecklistHistory(row) {
  return post("/history/checklists", row);
}

export function listChatHistory() {
  return request("/history/chats");
}

export function saveChatHistory(row) {
  return post("/history/chats", row);
}

export function listExportHistory() {
  return request("/history/exports");
}

export function saveExportHistory(row) {
  return post("/history/exports", row);
}
