"use client";

import { useSyncExternalStore } from "react";

/**
 * Chat bus: a tiny module store that lets any deal page open the "Ask the deal" panel with a prompt, so a finding,
 * a scenario run, or a missing document can hand the user straight into the conversation without retyping.
 *
 * Contract
 * - `askTheDeal(prompt, { send })` opens the panel and hands it one prompt. With `send: false` (the default) the
 *   panel prefills its textarea with the prompt and focuses it so the user can finish or edit the question; with
 *   `send: true` the panel sends the prompt as a message at once. Whitespace is trimmed and the text is capped at
 *   the API's message limit (4,000 characters); an empty prompt only opens the panel.
 * - Every call is a distinct request carrying a monotonically increasing `id`, so asking the same text twice is
 *   honoured twice. At most one request is pending: a newer call replaces one the panel has not taken yet.
 * - The panel receives requests through `onChatPrompt(cb)`: the callback runs at once for a request that is already
 *   pending when it subscribes, then for every new request. It calls `takeChatPrompt(id)` once it has acted on one;
 *   that returns true exactly once per id, so a React effect that runs twice (StrictMode) or a stale id cannot send a
 *   message twice.
 * - Closing the panel (`setChatOpen(false)`) discards a pending request: a prompt is meant for the session it opened.
 * - The store never touches the DOM and runs no effects. Components read it through `useChatBus()`
 *   (`useSyncExternalStore`); the server snapshot is the closed, empty state so SSR markup matches the first client
 *   render. Non-React code can read `getChatBusState()`.
 * - Prompts are plain user-facing text. The panel treats them exactly like typed input: they carry no markup, no
 *   citations, and no instructions for the model beyond what the user would type.
 */

export interface ChatPrompt { readonly id: number; readonly text: string; readonly send: boolean; readonly context?: string }
export interface ChatBusState { readonly open: boolean; readonly prompt: ChatPrompt | null }

/** Mirrors `ChatRequest.message` max_length in `api/routes/chat.py`. */
export const CHAT_PROMPT_MAX = 4000;

const CLOSED: ChatBusState = { open: false, prompt: null };
let state: ChatBusState = CLOSED;
let seq = 0;
const listeners = new Set<() => void>();
const promptListeners = new Set<(p: ChatPrompt) => void>();

function commit(next: ChatBusState): void {
  if (next.open === state.open && next.prompt === state.prompt) return;
  const arrived = next.prompt && next.prompt !== state.prompt ? next.prompt : null;
  state = next;
  listeners.forEach((l) => l());
  if (arrived) promptListeners.forEach((l) => l(arrived));
}

function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

/** Deliver prompts to the panel: a request already pending is delivered at once, then each new one as it arrives. */
export function onChatPrompt(cb: (p: ChatPrompt) => void): () => void {
  promptListeners.add(cb);
  if (state.prompt) cb(state.prompt);
  return () => { promptListeners.delete(cb); };
}

/** Open the panel with a prompt. `send: true` sends it immediately; otherwise it is prefilled for the user to finish. */
export function askTheDeal(prompt: string, opts: { send?: boolean; context?: string } = {}): void {
  const text = prompt.trim().slice(0, CHAT_PROMPT_MAX);
  if (!text) { commit({ open: true, prompt: state.prompt }); return; }
  seq += 1;
  commit({ open: true, prompt: { id: seq, text, send: opts.send === true, context: opts.context } });
}

/** Open or close the panel. Closing drops a prompt the panel has not taken. */
export function setChatOpen(open: boolean): void {
  commit(open ? { open: true, prompt: state.prompt } : CLOSED);
}

export function toggleChat(): void {
  setChatOpen(!state.open);
}

/** Acknowledge a prompt the panel acted on. True the first time for a pending id, false for a stale or repeated id. */
export function takeChatPrompt(id: number): boolean {
  if (!state.prompt || state.prompt.id !== id) return false;
  commit({ open: state.open, prompt: null });
  return true;
}

export function getChatBusState(): ChatBusState {
  return state;
}

/** Current bus state; re-renders the caller when the panel opens or closes or a prompt arrives or is taken. */
export function useChatBus(): ChatBusState {
  return useSyncExternalStore(subscribe, getChatBusState, () => CLOSED);
}

/** Back to the closed, empty state (tests). */
export function resetChatBus(): void {
  commit(CLOSED);
}
