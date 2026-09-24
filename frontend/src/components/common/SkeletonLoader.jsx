import React from "react";

export function SkeletonLoader({ type = "card", count = 1, className = "" }) {
  if (type === "card") {
    return (
      <div className={`grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 ${className}`}>
        {Array.from({ length: count }).map((_, i) => (
          <div
            key={i}
            className="p-5 rounded-2xl bg-white/5 border border-white/10 animate-pulse space-y-3"
          >
            <div className="h-3 w-1/3 bg-white/10 rounded"></div>
            <div className="h-7 w-2/3 bg-white/20 rounded"></div>
            <div className="h-2 w-1/2 bg-white/10 rounded"></div>
          </div>
        ))}
      </div>
    );
  }

  if (type === "table") {
    return (
      <div className={`w-full rounded-2xl bg-white/5 border border-white/10 p-4 animate-pulse space-y-3 ${className}`}>
        <div className="h-8 bg-white/10 rounded w-full"></div>
        {Array.from({ length: count || 5 }).map((_, i) => (
          <div key={i} className="flex gap-4 items-center">
            <div className="h-6 bg-white/10 rounded w-1/4"></div>
            <div className="h-6 bg-white/10 rounded w-1/4"></div>
            <div className="h-6 bg-white/10 rounded w-1/4"></div>
            <div className="h-6 bg-white/10 rounded w-1/4"></div>
          </div>
        ))}
      </div>
    );
  }

  if (type === "chart") {
    return (
      <div className={`w-full h-64 rounded-2xl bg-white/5 border border-white/10 p-6 flex flex-col justify-between animate-pulse ${className}`}>
        <div className="h-4 w-1/4 bg-white/10 rounded"></div>
        <div className="flex items-end gap-3 h-40">
          {Array.from({ length: 12 }).map((_, i) => (
            <div
              key={i}
              className="flex-1 bg-white/10 rounded-t"
              style={{ height: `${20 + ((i * 17) % 70)}%` }}
            ></div>
          ))}
        </div>
        <div className="h-3 w-1/2 bg-white/10 rounded"></div>
      </div>
    );
  }

  return (
    <div className={`h-10 bg-white/10 rounded animate-pulse ${className}`}></div>
  );
}

export default SkeletonLoader;
