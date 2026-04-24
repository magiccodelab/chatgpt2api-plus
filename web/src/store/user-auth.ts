"use client";

import localforage from "localforage";

export const USER_AUTH_KEY_STORAGE_KEY = "chatgpt2api_user_token";

const userAuthStorage = localforage.createInstance({
  name: "chatgpt2api",
  storeName: "user-auth",
});

export async function getStoredUserToken() {
  if (typeof window === "undefined") {
    return "";
  }
  const value = await userAuthStorage.getItem<string>(USER_AUTH_KEY_STORAGE_KEY);
  return String(value || "").trim();
}

export async function setStoredUserToken(token: string) {
  const normalized = String(token || "").trim();
  if (!normalized) {
    await clearStoredUserToken();
    return;
  }
  await userAuthStorage.setItem(USER_AUTH_KEY_STORAGE_KEY, normalized);
}

export async function clearStoredUserToken() {
  if (typeof window === "undefined") {
    return;
  }
  await userAuthStorage.removeItem(USER_AUTH_KEY_STORAGE_KEY);
}
