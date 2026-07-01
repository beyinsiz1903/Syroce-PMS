import React from "react";
import { Button } from "@/components/ui/button";

export default function LiteSetupBanner({ title, desc, actionLabel, onAction, secondaryLabel, onSecondary }) {
  return (
    <div className="mb-4 rounded-2xl border bg-white p-4">
      <div className="text-sm font-semibold text-gray-900">{title}</div>
      <div className="mt-1 text-sm text-gray-600">{desc}</div>
      <div className="mt-3 flex flex-wrap gap-2">
        {actionLabel ? (
          <Button size="sm" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
        {secondaryLabel ? (
          <Button size="sm" variant="outline" onClick={onSecondary}>
            {secondaryLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
