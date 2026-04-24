"use client";

import { Copy, KeyRound, LoaderCircle, Pencil, Plus, RotateCcw, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  createUserToken,
  deleteUserToken,
  fetchUserTokens,
  updateUserToken,
  type UserTokenItem,
} from "@/lib/api";

function formatDateTime(value: string | undefined | null) {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

async function copyToClipboard(text: string) {
  try {
    if (navigator?.clipboard) {
      await navigator.clipboard.writeText(text);
      toast.success("已复制到剪贴板");
      return;
    }
  } catch {
    // fallthrough
  }
  toast.error("复制失败，请手动复制");
}

export function UserTokensCard() {
  const [items, setItems] = useState<UserTokenItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  const [isFormOpen, setIsFormOpen] = useState(false);
  const [editing, setEditing] = useState<UserTokenItem | null>(null);
  const [formName, setFormName] = useState("");
  const [formLimit, setFormLimit] = useState("20");
  const [formNotes, setFormNotes] = useState("");
  const [isSaving, setIsSaving] = useState(false);

  const [newlyCreated, setNewlyCreated] = useState<{ id: string; token: string } | null>(null);

  const load = async () => {
    setIsLoading(true);
    try {
      const data = await fetchUserTokens();
      setItems(data.items);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "加载用户 Token 失败");
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const resetForm = () => {
    setEditing(null);
    setFormName("");
    setFormLimit("20");
    setFormNotes("");
  };

  const openAdd = () => {
    resetForm();
    setIsFormOpen(true);
  };

  const openEdit = (item: UserTokenItem) => {
    setEditing(item);
    setFormName(item.name);
    setFormLimit(String(item.daily_limit));
    setFormNotes(item.notes || "");
    setIsFormOpen(true);
  };

  const handleSave = async () => {
    const limitNumber = Number.parseInt(formLimit, 10);
    if (!Number.isFinite(limitNumber) || limitNumber < 0) {
      toast.error("每日额度需为非负整数");
      return;
    }
    setIsSaving(true);
    try {
      if (editing) {
        const data = await updateUserToken(editing.id, {
          name: formName.trim() || "未命名",
          daily_limit: limitNumber,
          notes: formNotes.trim(),
        });
        setItems(data.items);
        toast.success("已更新");
        setIsFormOpen(false);
        resetForm();
      } else {
        const data = await createUserToken({
          name: formName.trim() || "未命名",
          daily_limit: limitNumber,
          notes: formNotes.trim(),
        });
        setItems(data.items);
        const plain = data.item.token_plain || "";
        if (plain) {
          setNewlyCreated({ id: data.item.id, token: plain });
        }
        toast.success("Token 已创建（请立即复制，明文仅显示一次）");
        setIsFormOpen(false);
        resetForm();
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "保存失败");
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (item: UserTokenItem) => {
    if (typeof window !== "undefined" && !window.confirm(`确定删除 ${item.name || item.id}？`)) {
      return;
    }
    setBusyId(item.id);
    try {
      const data = await deleteUserToken(item.id);
      setItems(data.items);
      toast.success("已删除");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "删除失败");
    } finally {
      setBusyId(null);
    }
  };

  const handleResetUsage = async (item: UserTokenItem) => {
    setBusyId(item.id);
    try {
      const data = await updateUserToken(item.id, { reset_usage: true });
      setItems(data.items);
      toast.success("今日用量已重置");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "重置失败");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <Card className="rounded-2xl border-white/80 bg-white/90 shadow-sm">
      <CardContent className="space-y-6 p-6">
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-stone-100">
              <KeyRound className="size-5 text-stone-600" />
            </div>
            <div>
              <h2 className="text-lg font-semibold tracking-tight">用户 Token 管理</h2>
              <p className="text-sm text-stone-500">
                面向 <code className="rounded bg-stone-100 px-1">/u</code> 用户端的令牌，按用户分配每日额度，每天
                00:00（UTC+8）自动重置。
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {items.length > 0 ? <Badge className="rounded-md px-2.5 py-1">{items.length} 个用户</Badge> : null}
            <Button className="h-9 rounded-xl bg-stone-950 px-4 text-white hover:bg-stone-800" onClick={openAdd}>
              <Plus className="size-4" />
              新建 Token
            </Button>
          </div>
        </div>

        {newlyCreated ? (
          <div className="space-y-2 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            <div className="font-medium">新 Token 已生成（明文仅显示这一次）</div>
            <div className="flex items-center gap-2">
              <code className="flex-1 break-all rounded bg-white px-2 py-1 font-mono text-xs text-stone-800">
                {newlyCreated.token}
              </code>
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-lg border-amber-300 bg-white px-3 text-amber-700"
                onClick={() => void copyToClipboard(newlyCreated.token)}
              >
                <Copy className="size-3.5" />
                复制
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-8 rounded-lg px-3 text-amber-700 hover:bg-amber-100"
                onClick={() => setNewlyCreated(null)}
              >
                关闭
              </Button>
            </div>
          </div>
        ) : null}

        {isFormOpen ? (
          <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 px-4 py-4">
            <div className="text-sm font-medium text-stone-700">{editing ? "编辑 Token" : "新建 Token"}</div>
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
              <div className="space-y-1">
                <label className="text-xs text-stone-500">名称</label>
                <Input value={formName} onChange={(event) => setFormName(event.target.value)} placeholder="比如 小张" />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-stone-500">每日额度</label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  value={formLimit}
                  onChange={(event) => setFormLimit(event.target.value)}
                />
              </div>
              <div className="space-y-1">
                <label className="text-xs text-stone-500">备注（可选）</label>
                <Input value={formNotes} onChange={(event) => setFormNotes(event.target.value)} placeholder="备注信息" />
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                className="h-9 rounded-lg border-stone-200 bg-white px-4"
                onClick={() => {
                  setIsFormOpen(false);
                  resetForm();
                }}
                disabled={isSaving}
              >
                取消
              </Button>
              <Button
                className="h-9 rounded-lg bg-stone-950 px-4 text-white hover:bg-stone-800"
                onClick={() => void handleSave()}
                disabled={isSaving}
              >
                {isSaving ? <LoaderCircle className="size-4 animate-spin" /> : null}
                保存
              </Button>
            </div>
          </div>
        ) : null}

        {isLoading ? (
          <div className="flex items-center justify-center py-10">
            <LoaderCircle className="size-5 animate-spin text-stone-400" />
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-3 rounded-xl bg-stone-50 px-6 py-10 text-center">
            <KeyRound className="size-8 text-stone-300" />
            <div className="space-y-1">
              <p className="text-sm font-medium text-stone-600">暂无用户 Token</p>
              <p className="text-sm text-stone-400">点击「新建 Token」为用户分配访问令牌与每日额度。</p>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            {items.map((item) => {
              const isBusy = busyId === item.id;
              const percent = item.daily_limit > 0 ? Math.round((item.used_today / item.daily_limit) * 100) : 0;
              return (
                <div
                  key={item.id}
                  className="flex flex-col gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 text-sm font-medium text-stone-800">
                        {item.name || "未命名"}
                        <code className="rounded bg-stone-100 px-1.5 py-0.5 font-mono text-xs text-stone-500">
                          {item.token_masked}
                        </code>
                      </div>
                      {item.notes ? <div className="truncate text-xs text-stone-400">{item.notes}</div> : null}
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 disabled:opacity-60"
                        onClick={() => openEdit(item)}
                        disabled={isBusy}
                        title="编辑"
                      >
                        <Pencil className="size-4" />
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-stone-100 hover:text-stone-700 disabled:opacity-60"
                        onClick={() => void handleResetUsage(item)}
                        disabled={isBusy}
                        title="重置今日用量"
                      >
                        {isBusy ? <LoaderCircle className="size-4 animate-spin" /> : <RotateCcw className="size-4" />}
                      </button>
                      <button
                        type="button"
                        className="rounded-lg p-2 text-stone-400 transition hover:bg-rose-50 hover:text-rose-500 disabled:opacity-60"
                        onClick={() => void handleDelete(item)}
                        disabled={isBusy}
                        title="删除"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-3 text-xs text-stone-500">
                    <span>
                      今日已用 <span className="font-medium text-stone-700">{item.used_today}</span> /{" "}
                      {item.daily_limit}
                    </span>
                    <span>剩余 {item.remaining}</span>
                    <span>下次重置 {formatDateTime(item.reset_at)}</span>
                    <span>更新 {formatDateTime(item.updated_at)}</span>
                  </div>

                  <div className="h-1.5 overflow-hidden rounded-full bg-stone-100">
                    <div
                      className="h-full rounded-full bg-stone-900 transition-all"
                      style={{ width: `${Math.min(100, percent)}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
