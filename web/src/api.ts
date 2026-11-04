let token = sessionStorage.getItem("swarm-token") || "";
export function setToken(value: string) {
  token = value;
  if (value) sessionStorage.setItem("swarm-token", value);
  else sessionStorage.removeItem("swarm-token");
}
export function getToken() {
  return token;
}
export async function api(path: string, method = "GET", body?: unknown) {
  const response = await fetch("/api/v1" + path, {
    method,
    headers: {
      Authorization: "Bearer " + token,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (response.status === 401 && path != "/auth/login") {
    setToken("");
    window.dispatchEvent(new Event("swarm-logout"));
  }
  if (!response.ok) {
    const data = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : JSON.stringify(data.detail),
    );
  }
  return response.json();
}
export async function download(path: string, name: string) {
  const r = await fetch("/api/v1" + path, {
    headers: { Authorization: "Bearer " + token },
  });
  if (!r.ok) throw new Error("Download failed: " + r.status);
  const url = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
