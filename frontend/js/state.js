// Shared client state and a tiny event bus.

import { get } from "./api.js";
import { storage } from "./dom.js";

const CONNECTION_KEY = "abiet.connection";

export const state = {
  info: null,
  user: null,
  connections: [],
  connectionId: Number(storage.get(CONNECTION_KEY)) || null,
  types: null,
  schemas: new Map(),
};

const listeners = new Map();

export function on(event, fn) {
  if (!listeners.has(event)) listeners.set(event, new Set());
  listeners.get(event).add(fn);
  return () => listeners.get(event).delete(fn);
}

export function emit(event, payload) {
  // Iterate over a copy: handlers may subscribe or unsubscribe while running.
  for (const fn of [...(listeners.get(event) || [])]) fn(payload);
}

export function currentConnection() {
  return state.connections.find((c) => c.id === state.connectionId) || null;
}

export function selectConnection(id) {
  const next = id == null ? null : Number(id);
  if (next === state.connectionId) return;
  state.connectionId = next;
  storage.set(CONNECTION_KEY, next);
  emit("connection", currentConnection());
}

export async function loadConnections() {
  const previous = state.connectionId;
  state.connections = await get("/connections");
  if (!state.connections.some((c) => c.id === state.connectionId)) {
    state.connectionId = state.connections[0]?.id ?? null;
    storage.set(CONNECTION_KEY, state.connectionId);
  }
  emit("connections", state.connections);
  if (state.connectionId !== previous) emit("connection", currentConnection());
  return state.connections;
}

export async function loadTypes() {
  state.types ||= await get("/connections/types");
  return state.types;
}

export async function loadSchema(connectionId, refresh = false) {
  if (!refresh && state.schemas.has(connectionId)) return state.schemas.get(connectionId);
  const schema = await get(`/connections/${connectionId}/schema${refresh ? "?refresh=true" : ""}`);
  state.schemas.set(connectionId, schema);
  return schema;
}

export function forgetSchema(connectionId) {
  state.schemas.delete(connectionId);
}
