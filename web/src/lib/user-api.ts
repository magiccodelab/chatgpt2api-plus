import { userHttpRequest } from "@/lib/user-request";

export type UserQuotaStatus = {
  name: string;
  daily_limit: number;
  used_today: number;
  remaining: number;
  last_reset_date: string | null;
  reset_at: string;
};

type ImageResponsePayload = {
  created: number;
  data: Array<{ b64_json: string; revised_prompt?: string }>;
  usage?: UserQuotaStatus;
};

export async function userLogin(token: string) {
  const normalized = String(token || "").trim();
  return userHttpRequest<{ ok: boolean; status: UserQuotaStatus }>("/api/user/auth/login", {
    method: "POST",
    body: {},
    headers: {
      Authorization: `Bearer ${normalized}`,
    },
    redirectOnUnauthorized: false,
  });
}

export async function fetchUserMe() {
  return userHttpRequest<{ status: UserQuotaStatus }>("/api/user/me");
}

export async function userGenerateImage(prompt: string, model?: string) {
  return userHttpRequest<ImageResponsePayload>("/api/user/images/generations", {
    method: "POST",
    body: {
      prompt,
      ...(model ? { model } : {}),
    },
  });
}

export async function userEditImage(files: File | File[], prompt: string, model?: string) {
  const formData = new FormData();
  const uploadFiles = Array.isArray(files) ? files : [files];
  uploadFiles.forEach((file) => {
    formData.append("image", file);
  });
  formData.append("prompt", prompt);
  if (model) {
    formData.append("model", model);
  }

  return userHttpRequest<ImageResponsePayload>("/api/user/images/edits", {
    method: "POST",
    body: formData,
  });
}
