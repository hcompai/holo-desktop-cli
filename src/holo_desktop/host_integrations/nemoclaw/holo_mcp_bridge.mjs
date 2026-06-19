import { promises as fs } from "fs";
import path from "path";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

const bridgePort = process.env.HOLO_BRIDGE_PORT || "19131";
const bridgeUrl = process.env.HOLO_BRIDGE_URL || `http://host.openshell.internal:${bridgePort}`;
const bridgeToken = process.env.HOLO_BRIDGE_TOKEN || "";
const openClawMediaRoot = process.env.OPENCLAW_MEDIA_ROOT || "/sandbox/.openclaw/media";
const maxMediaBytes = Number(process.env.HOLO_BRIDGE_MAX_MEDIA_BYTES || 10 * 1024 * 1024);

function headers() {
  const out = { "content-type": "application/json" };
  if (bridgeToken) out.authorization = `Bearer ${bridgeToken}`;
  return out;
}

async function mediaPayload(mediaPaths) {
  const media = [];
  for (const mediaPath of mediaPaths || []) {
    const resolvedPath = await resolveMediaPath(mediaPath);
    const stat = await fs.stat(resolvedPath);
    if (!stat.isFile()) {
      throw new Error(`media path is not a file: ${mediaPath}`);
    }
    if (stat.size > maxMediaBytes) {
      throw new Error(`media file is too large: ${mediaPath}`);
    }
    const data = await fs.readFile(resolvedPath);
    media.push({
      name: path.basename(resolvedPath),
      source_path: mediaPath,
      resolved_path: resolvedPath,
      data_base64: data.toString("base64"),
    });
  }
  return media;
}

async function resolveMediaPath(mediaPath) {
  if (!mediaPath.startsWith("media://")) {
    throw new Error("media_paths must use media:// URIs");
  }
  const mediaRelativePath = mediaPath.slice("media://".length).replace(/^\/+/, "");
  if (!mediaRelativePath) {
    throw new Error("media:// URI must include a relative path");
  }
  const rootPath = await fs.realpath(openClawMediaRoot);
  const candidatePath = path.resolve(rootPath, mediaRelativePath);
  const resolvedPath = await fs.realpath(candidatePath);
  if (!isWithinMediaRoot(rootPath, resolvedPath)) {
    throw new Error(`media path escapes ${openClawMediaRoot}: ${mediaPath}`);
  }
  return resolvedPath;
}

function isWithinMediaRoot(rootPath, candidatePath) {
  const relative = path.relative(rootPath, candidatePath);
  return relative === "" || (!!relative && !relative.startsWith("..") && !path.isAbsolute(relative));
}

async function post(pathName, body) {
  const response = await fetch(`${bridgeUrl}${pathName}`, {
    method: "POST",
    headers: headers(),
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let data;
  try {
    data = JSON.parse(text);
  } catch {
    data = { ok: false, error: text };
  }
  if (!response.ok) {
    return { ok: false, error: data.error || text || `HTTP ${response.status}` };
  }
  return data;
}

function resultText(data) {
  const chunks = [];
  if (data.status) chunks.push(`status=${data.status}`);
  if (data.run_id) chunks.push(`run_id=${data.run_id}`);
  if (data.message) chunks.push(data.message);
  if (data.returncode !== undefined) chunks.push(`returncode=${data.returncode}`);
  if (data.stdout) chunks.push(`stdout:\n${data.stdout}`);
  if (data.stderr) chunks.push(`stderr:\n${data.stderr}`);
  if (data.error) chunks.push(`error: ${data.error}`);
  return chunks.join("\n\n") || JSON.stringify(data);
}

const taskSchema = {
  task: z.string().min(1),
  media_paths: z.array(z.string().min(1)).optional(),
};

const server = new McpServer({ name: "holo-desktop-bridge", version: "0.0.1" });

server.tool(
  "holo_desktop_launch",
  "Start one HoloDesktop task on the host desktop and return a run_id. Do not answer the user yet; call holo_desktop_poll with that same run_id until status is completed or failed. Pass local sandbox media_paths for images/files that Holo should use.",
  taskSchema,
  async ({ task, media_paths }) => {
    try {
      const data = await post("/launch", { task, media: await mediaPayload(media_paths) });
      return { isError: !data.ok, content: [{ type: "text", text: resultText(data) }] };
    } catch (error) {
      return { isError: true, content: [{ type: "text", text: error.message || String(error) }] };
    }
  },
);

server.tool(
  "holo_desktop_poll",
  "Poll a HoloDesktop task started with holo_desktop_launch. This waits briefly. If status is running, call holo_desktop_poll again with the same run_id now; do not launch another task and do not ask the user to poll.",
  { run_id: z.string().min(1) },
  async ({ run_id }) => {
    try {
      const data = await post("/poll", { run_id });
      return { isError: !data.ok, content: [{ type: "text", text: resultText(data) }] };
    } catch (error) {
      return { isError: true, content: [{ type: "text", text: error.message || String(error) }] };
    }
  },
);

server.tool(
  "holo_desktop_kill",
  "Cancel a HoloDesktop task started with holo_desktop_launch.",
  { run_id: z.string().min(1) },
  async ({ run_id }) => {
    try {
      const data = await post("/kill", { run_id });
      return { isError: !data.ok, content: [{ type: "text", text: resultText(data) }] };
    } catch (error) {
      return { isError: true, content: [{ type: "text", text: error.message || String(error) }] };
    }
  },
);

await server.connect(new StdioServerTransport());
