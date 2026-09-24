import React from "react";
import { FolderOpen, ArrowRight, UploadCloud, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";

export function EmptyState({
  title = "No Data Available",
  description = "Get started by importing your sales transactions, demand records, or uploading a sample dataset.",
  actionText = "Upload Data",
  actionLink = "/upload",
  onActionClick = null,
  showSampleHint = true,
  icon: Icon = FolderOpen,
}) {
  const navigate = useNavigate();

  const handleAction = () => {
    if (onActionClick) {
      onActionClick();
    } else if (actionLink) {
      navigate(actionLink);
    }
  };

  return (
    <div className="flex flex-col items-center justify-center p-12 text-center rounded-3xl border border-dashed border-white/15 bg-white/[0.02] backdrop-blur-sm">
      <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 mb-4 shadow-lg shadow-indigo-500/5">
        <Icon className="w-8 h-8" />
      </div>

      <h3 className="text-xl font-bold text-white mb-2">{title}</h3>
      <p className="text-sm text-slate-400 max-w-md mb-6 leading-relaxed">
        {description}
      </p>

      <div className="flex flex-wrap gap-3 justify-center">
        <button
          onClick={handleAction}
          className="inline-flex items-center gap-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-indigo-500 to-indigo-600 hover:from-indigo-600 hover:to-indigo-700 text-white font-medium shadow-lg shadow-indigo-500/20 transition-all text-sm"
        >
          <UploadCloud className="w-4 h-4" />
          {actionText}
          <ArrowRight className="w-4 h-4" />
        </button>
      </div>

      {showSampleHint && (
        <div className="mt-8 pt-6 border-t border-white/5 text-xs text-slate-500 flex items-center gap-2">
          <span>💡 Tip: Ensure your CSV includes</span>
          <code className="bg-white/5 text-indigo-300 px-2 py-0.5 rounded border border-white/10">date</code>
          <code className="bg-white/5 text-indigo-300 px-2 py-0.5 rounded border border-white/10">product_id</code>
          <code className="bg-white/5 text-indigo-300 px-2 py-0.5 rounded border border-white/10">quantity</code>
        </div>
      )}
    </div>
  );
}

export default EmptyState;
