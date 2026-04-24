"use client";

import { LoaderCircle, PlugZap } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { testProxy, type ProxyTestResult } from "@/lib/api";

interface ProxyInputProps {
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
  helperText?: string;
}

export function ProxyInput({
  value,
  onChange,
  disabled,
  placeholder = "http://host:port 或 socks5://user:pass@host:port",
  helperText = "留空表示不使用账号级代理。",
}: ProxyInputProps) {
  const [isTesting, setIsTesting] = useState(false);
  const [result, setResult] = useState<ProxyTestResult | null>(null);

  const handleTest = async () => {
    const candidate = value.trim();
    if (!candidate) {
      toast.error("请先填写代理地址");
      return;
    }
    setIsTesting(true);
    setResult(null);
    try {
      const data = await testProxy(candidate);
      setResult(data.result);
      if (data.result.ok) {
        toast.success(`代理可用（${data.result.latency_ms} ms，HTTP ${data.result.status}）`);
      } else {
        toast.error(`代理不可用：${data.result.error ?? "未知错误"}`);
      }
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "测试代理失败");
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="space-y-2">
      <Input
        value={value}
        onChange={(event) => {
          onChange(event.target.value);
          setResult(null);
        }}
        placeholder={placeholder}
        disabled={disabled}
        className="h-10 rounded-xl border-stone-200 bg-white"
      />
      <p className="text-xs text-stone-500">
        {helperText}
        <span className="ml-1 text-stone-400">
          支持 http / https / socks5 / socks5h；SOCKS5H 使用远端 DNS。
        </span>
      </p>
      {result ? (
        <div
          className={`rounded-xl border px-3 py-2 text-xs leading-6 ${
            result.ok
              ? "border-emerald-200 bg-emerald-50 text-emerald-800"
              : "border-rose-200 bg-rose-50 text-rose-800"
          }`}
        >
          {result.ok
            ? `代理可用：HTTP ${result.status}，用时 ${result.latency_ms} ms`
            : `代理不可用：${result.error ?? "未知错误"}（用时 ${result.latency_ms} ms）`}
        </div>
      ) : null}
      <div className="flex justify-end">
        <Button
          type="button"
          variant="outline"
          className="h-9 rounded-xl border-stone-200 bg-white px-4 text-stone-700"
          onClick={() => void handleTest()}
          disabled={disabled || isTesting}
        >
          {isTesting ? <LoaderCircle className="size-4 animate-spin" /> : <PlugZap className="size-4" />}
          测试代理
        </Button>
      </div>
    </div>
  );
}

export function maskProxyUrl(url: string): string {
  const trimmed = url.trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed);
    if (parsed.username || parsed.password) {
      parsed.username = "***";
      parsed.password = "";
    }
    return parsed.toString().replace(/\/$/, "");
  } catch {
    return trimmed;
  }
}
