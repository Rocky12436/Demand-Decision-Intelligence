import { useEffect, useState, useMemo } from "react";
import {
  uploadSalesFile,
  getUploads,
  resolveSkus,
  getProducts,
  getFailedRowsDownloadUrl,
} from "../../services/api";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [uploads, setUploads] = useState([]);
  const [products, setProducts] = useState([]);
  const [skuSelections, setSkuSelections] = useState({});
  const [resolving, setResolving] = useState(false);
  const [resolveSuccessMsg, setResolveSuccessMsg] = useState("");

  const loadUploads = async () => {
    try {
      const data = await getUploads();
      setUploads(data.uploads || []);
    } catch (err) {
      console.error("Failed to load uploads:", err);
    }
  };

  const loadProducts = async () => {
    try {
      const prods = await getProducts(200);
      setProducts(prods || []);
    } catch (err) {
      console.error("Failed to load products list:", err);
    }
  };

  useEffect(() => {
    loadUploads();
    loadProducts();
  }, []);

  // Initialize SKU selections whenever result changes
  useEffect(() => {
    if (result && result.unmapped_skus && Array.isArray(result.unmapped_skus)) {
      const initial = {};
      result.unmapped_skus.forEach((item) => {
        const sku = typeof item === "string" ? item : item.sku;
        const suggestion = item.suggested_mapping?.product_id;
        const confidence = item.suggested_mapping?.confidence || 0;
        // Pre-fill if confidence is high (>= 0.75)
        if (suggestion && confidence >= 0.75) {
          initial[sku] = suggestion;
        } else {
          initial[sku] = "";
        }
      });
      setSkuSelections(initial);
    }
  }, [result]);

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];
    setError("");
    setResult(null);
    setResolveSuccessMsg("");

    if (!selectedFile) {
      setFile(null);
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
      setError("Please select a valid CSV file.");
      setFile(null);
      return;
    }

    setFile(selectedFile);
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a CSV file first.");
      return;
    }

    try {
      setUploading(true);
      setError("");
      setResult(null);
      setResolveSuccessMsg("");

      const data = await uploadSalesFile(file);
      setResult(data);
      await loadUploads();
      setFile(null);
    } catch (err) {
      setError(err.message || "Upload failed");
    } finally {
      setUploading(false);
    }
  };

  // Determine state strictly: SUCCESS (green), PARTIAL (amber), REJECTED (red)
  // Never show green checkmark when valid_rows == 0
  const uploadState = useMemo(() => {
    if (!result) return null;
    const valid = Number(result.valid_rows || 0);
    const invalid = Number(result.invalid_rows || (result.total_rows ? result.total_rows - valid : 0));
    const status = String(result.status || "").toUpperCase();

    if (valid === 0 || status === "REJECTED" || status === "FAILED") {
      return "REJECTED";
    }
    if (invalid > 0 || status === "PARTIAL") {
      return "PARTIAL";
    }
    return "SUCCESS";
  }, [result]);

  // Compute stat row figures
  const stats = useMemo(() => {
    if (!result) return null;
    const total = Number(result.total_rows || 0);
    const valid = Number(result.valid_rows || 0);
    const errors = Number(result.invalid_rows || (total > valid ? total - valid : 0));
    const percentAccepted = total > 0 ? ((valid / total) * 100).toFixed(1) : "0.0";
    return { total, valid, errors, percentAccepted };
  }, [result]);

  // Sort error breakdown largest category first
  const sortedErrorBreakdown = useMemo(() => {
    if (!result || !result.error_breakdown) return [];
    return Object.entries(result.error_breakdown).sort((a, b) => b[1] - a[1]);
  }, [result]);

  // Handle SKU mapping global actions
  const handleApplyAllSuggestions = () => {
    if (!result || !result.unmapped_skus) return;
    const updated = { ...skuSelections };
    result.unmapped_skus.forEach((item) => {
      const sku = typeof item === "string" ? item : item.sku;
      if (item.suggested_mapping?.product_id) {
        updated[sku] = item.suggested_mapping.product_id;
      }
    });
    setSkuSelections(updated);
  };

  const handleCreateAllAsNew = () => {
    if (!result || !result.unmapped_skus) return;
    const updated = { ...skuSelections };
    result.unmapped_skus.forEach((item) => {
      const sku = typeof item === "string" ? item : item.sku;
      updated[sku] = "__CREATE_NEW__";
    });
    setSkuSelections(updated);
  };

  const handleResolveSkusSubmit = async () => {
    if (!result || !result.upload_id) return;
    try {
      setResolving(true);
      setError("");
      setResolveSuccessMsg("");

      const mappingsPayload = Object.entries(skuSelections).map(([raw_sku, val]) => ({
        raw_sku,
        resolved_product_id: val === "__CREATE_NEW__" ? raw_sku : (val || raw_sku),
        create_new: val === "__CREATE_NEW__",
      }));

      const res = await resolveSkus(result.upload_id, mappingsPayload);
      setResolveSuccessMsg(
        `Successfully resolved SKU mappings! Re-ingested ${res.re_ingested_rows || 0} previously failed rows.`
      );

      // Refresh upload state with latest counts
      setResult((prev) => ({
        ...prev,
        status: res.remaining_errors > 0 ? "PARTIAL" : "SUCCESS",
        valid_rows: (prev.valid_rows || 0) + (res.re_ingested_rows || 0),
        invalid_rows: res.remaining_errors || 0,
        unmapped_skus: res.remaining_unmapped_skus || [],
      }));

      await loadUploads();
      await loadProducts();
    } catch (err) {
      setError(err.message || "Failed to resolve SKU mappings");
    } finally {
      setResolving(false);
    }
  };

  return (
    <div className="p-6 space-y-8 max-w-7xl mx-auto">
      {/* Page Header */}
      <div>
        <h1 className="text-3xl font-bold text-gray-900 tracking-tight">
          Data Ingestion & Quality Validation
        </h1>
        <p className="text-gray-600 mt-2 text-sm leading-relaxed">
          Upload sales transactions CSV. Ingestion strictly validates row schemas, price boundaries, and SKU mappings before committing to the database.
        </p>
      </div>

      {/* Upload Input Card */}
      <div className="border border-gray-200 rounded-xl p-6 bg-white shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Upload Sales Data
        </h2>

        <div className="flex flex-col sm:flex-row gap-4 items-start sm:items-center">
          <input
            type="file"
            accept=".csv"
            onChange={handleFileChange}
            className="block w-full text-sm text-gray-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100 border border-gray-300 rounded-lg p-2"
          />

          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="px-6 py-2.5 rounded-lg bg-gray-900 hover:bg-gray-800 text-white font-medium text-sm disabled:opacity-50 transition-colors shrink-0 shadow-sm"
          >
            {uploading ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
                </svg>
                Validating & Ingesting...
              </span>
            ) : (
              "Upload CSV"
            )}
          </button>
        </div>

        {file && (
          <div className="mt-4 p-3 bg-gray-50 border border-gray-100 rounded-lg text-sm flex justify-between items-center">
            <span className="font-medium text-gray-700">Selected: {file.name}</span>
            <span className="text-gray-500">{(file.size / 1024).toFixed(2)} KB</span>
          </div>
        )}

        {error && (
          <div className="mt-4 p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm flex items-start gap-2">
            <span className="font-bold">Error:</span> {error}
          </div>
        )}

        {resolveSuccessMsg && (
          <div className="mt-4 p-4 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-sm font-medium">
            ✓ {resolveSuccessMsg}
          </div>
        )}
      </div>

      {/* Upload Result View - 3 Distinct States */}
      {result && stats && (
        <div
          className={`border rounded-xl p-6 shadow-sm transition-all ${
            uploadState === "SUCCESS"
              ? "bg-emerald-50/40 border-emerald-200"
              : uploadState === "PARTIAL"
              ? "bg-amber-50/40 border-amber-200"
              : "bg-red-50/40 border-red-200"
          }`}
        >
          {/* Header Banner with State */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-5 border-b border-gray-200/60">
            <div className="flex items-center gap-3">
              {uploadState === "SUCCESS" && (
                <div className="w-10 h-10 rounded-full bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold text-lg shadow-sm">
                  ✓
                </div>
              )}
              {uploadState === "PARTIAL" && (
                <div className="w-10 h-10 rounded-full bg-amber-100 text-amber-700 flex items-center justify-center font-bold text-lg shadow-sm">
                  ⚠
                </div>
              )}
              {uploadState === "REJECTED" && (
                <div className="w-10 h-10 rounded-full bg-red-100 text-red-700 flex items-center justify-center font-bold text-lg shadow-sm">
                  ✕
                </div>
              )}

              <div>
                <h2 className="text-xl font-bold text-gray-900">
                  {uploadState === "SUCCESS" && "Upload Succeeded (100% Ingested)"}
                  {uploadState === "PARTIAL" && "Partially Ingested (Validation Warnings)"}
                  {uploadState === "REJECTED" && "Upload Rejected (0 Valid Rows Ingested)"}
                </h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Job ID: {result.upload_id || result.id || "N/A"} • File: {result.filename || "Uploaded CSV"}
                </p>
              </div>
            </div>

            {/* Download Failed Rows Button */}
            {stats.errors > 0 && result.upload_id && (
              <a
                href={getFailedRowsDownloadUrl(result.upload_id)}
                download={`failed_rows_${result.upload_id}.csv`}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-white border border-gray-300 text-gray-700 text-sm font-medium hover:bg-gray-50 shadow-sm transition-colors shrink-0"
              >
                <svg className="w-4 h-4 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download Failed Rows ({stats.errors})
              </a>
            )}
          </div>

          {/* Stat Row: Total Rows / Valid / Errors / % Accepted */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mt-6">
            <div className="bg-white p-4 rounded-lg border border-gray-200/80 shadow-xs">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Total Rows</p>
              <p className="text-2xl font-extrabold text-gray-900 mt-1">{stats.total.toLocaleString()}</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200/80 shadow-xs">
              <p className="text-xs font-semibold text-emerald-600 uppercase tracking-wider">Valid Rows</p>
              <p className="text-2xl font-extrabold text-emerald-700 mt-1">{stats.valid.toLocaleString()}</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200/80 shadow-xs">
              <p className="text-xs font-semibold text-red-600 uppercase tracking-wider">Error Rows</p>
              <p className="text-2xl font-extrabold text-red-700 mt-1">{stats.errors.toLocaleString()}</p>
            </div>
            <div className="bg-white p-4 rounded-lg border border-gray-200/80 shadow-xs">
              <p className="text-xs font-semibold text-blue-600 uppercase tracking-wider">% Accepted</p>
              <p className="text-2xl font-extrabold text-blue-700 mt-1">{stats.percentAccepted}%</p>
            </div>
          </div>

          {/* Error Breakdown: Largest Category First */}
          {sortedErrorBreakdown.length > 0 && (
            <div className="mt-6 bg-white p-5 rounded-lg border border-gray-200/80">
              <h3 className="text-sm font-bold text-gray-900 uppercase tracking-wide mb-3 flex items-center justify-between">
                <span>Validation Failure Breakdown</span>
                <span className="text-xs font-normal text-gray-500">Sorted by frequency</span>
              </h3>
              <div className="space-y-3">
                {sortedErrorBreakdown.map(([category, count]) => {
                  const pct = stats.errors > 0 ? ((count / stats.errors) * 100).toFixed(1) : 0;
                  return (
                    <div key={category} className="space-y-1">
                      <div className="flex justify-between text-xs font-medium text-gray-700">
                        <span className="capitalize">{category.replace(/_/g, " ")}</span>
                        <span>
                          {count} rows ({pct}%)
                        </span>
                      </div>
                      <div className="w-full bg-gray-100 h-2 rounded-full overflow-hidden">
                        <div
                          className="bg-red-500 h-2 rounded-full transition-all duration-300"
                          style={{ width: `${pct}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* SKU Mapping Panel */}
          {result.unmapped_skus && result.unmapped_skus.length > 0 && (
            <div className="mt-6 bg-white p-5 rounded-lg border border-amber-200/90 shadow-sm">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-gray-100">
                <div>
                  <h3 className="text-base font-bold text-gray-900 flex items-center gap-2">
                    <span className="inline-block w-2.5 h-2.5 rounded-full bg-amber-500" />
                    Unmapped SKU Resolution Panel ({result.unmapped_skus.length} Unmatched)
                  </h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Map incoming SKUs to existing product IDs or provision them as new catalog entries.
                  </p>
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <button
                    onClick={handleApplyAllSuggestions}
                    className="px-3 py-1.5 text-xs font-medium bg-blue-50 text-blue-700 hover:bg-blue-100 rounded-md transition-colors"
                  >
                    Apply All Suggestions
                  </button>
                  <button
                    onClick={handleCreateAllAsNew}
                    className="px-3 py-1.5 text-xs font-medium bg-gray-100 text-gray-700 hover:bg-gray-200 rounded-md transition-colors"
                  >
                    Create All as New
                  </button>
                </div>
              </div>

              <div className="mt-4 overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b text-xs font-semibold text-gray-500 uppercase">
                      <th className="py-2 px-3">Unmapped SKU</th>
                      <th className="py-2 px-3">Occurrences</th>
                      <th className="py-2 px-3">Suggested Product</th>
                      <th className="py-2 px-3">Resolution Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {result.unmapped_skus.map((item, idx) => {
                      const sku = typeof item === "string" ? item : item.sku;
                      const count = typeof item === "object" ? item.occurrences || 1 : 1;
                      const suggested = item.suggested_mapping?.product_id;
                      const conf = item.suggested_mapping?.confidence;

                      return (
                        <tr key={sku || idx} className="hover:bg-gray-50/80">
                          <td className="py-2.5 px-3 font-mono font-semibold text-gray-800">
                            {sku}
                          </td>
                          <td className="py-2.5 px-3 text-gray-600">
                            {count}
                          </td>
                          <td className="py-2.5 px-3">
                            {suggested ? (
                              <div className="flex items-center gap-2">
                                <span className="font-medium text-gray-900">{suggested}</span>
                                {conf && (
                                  <span className="text-xs px-2 py-0.5 rounded-full bg-blue-100 text-blue-700 font-semibold">
                                    {(conf * 100).toFixed(0)}% match
                                  </span>
                                )}
                              </div>
                            ) : (
                              <span className="text-xs text-gray-400 italic">No suggestion</span>
                            )}
                          </td>
                          <td className="py-2.5 px-3">
                            <select
                              value={skuSelections[sku] || ""}
                              onChange={(e) =>
                                setSkuSelections((prev) => ({
                                  ...prev,
                                  [sku]: e.target.value,
                                }))
                              }
                              className="border border-gray-300 rounded-md px-2.5 py-1.5 text-xs bg-white text-gray-800 focus:ring-1 focus:ring-blue-500 w-full max-w-xs"
                            >
                              <option value="">-- Select resolution --</option>
                              {suggested && (
                                <option value={suggested}>
                                  Map to Suggested: {suggested}
                                </option>
                              )}
                              <option value="__CREATE_NEW__">
                                ＋ Create as new product
                              </option>
                              <optgroup label="Catalog Products">
                                {products.map((p) => (
                                  <option key={p.product_id} value={p.product_id}>
                                    {p.product_id} - {p.product_name || "Unnamed"}
                                  </option>
                                ))}
                              </optgroup>
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>

              <div className="mt-5 flex justify-end">
                <button
                  onClick={handleResolveSkusSubmit}
                  disabled={resolving}
                  className="px-5 py-2.5 rounded-lg bg-emerald-700 hover:bg-emerald-800 text-white font-medium text-sm disabled:opacity-50 transition-colors shadow-sm flex items-center gap-2"
                >
                  {resolving ? "Re-Ingesting Failed Rows..." : "Resolve & Re-Ingest Failed Rows"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Upload History Table */}
      <div className="border border-gray-200 rounded-xl p-6 bg-white shadow-sm">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">
          Ingestion History & Provenance
        </h2>

        {uploads.length === 0 ? (
          <p className="text-gray-500 text-sm">No upload history available.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b text-xs font-semibold text-gray-500 uppercase">
                  <th className="py-3 px-3">Job ID</th>
                  <th className="py-3 px-3">File</th>
                  <th className="py-3 px-3">Status</th>
                  <th className="py-3 px-3">Total Rows</th>
                  <th className="py-3 px-3">Processed</th>
                  <th className="py-3 px-3">Date</th>
                  <th className="py-3 px-3">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {uploads.map((upload) => (
                  <tr key={upload.id} className="hover:bg-gray-50/60">
                    <td className="py-3 px-3 font-mono text-gray-600">#{upload.id}</td>
                    <td className="py-3 px-3 font-medium text-gray-900">{upload.filename}</td>
                    <td className="py-3 px-3">
                      <span
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold ${
                          upload.status === "COMPLETED" || upload.status === "SUCCESS"
                            ? "bg-emerald-100 text-emerald-800"
                            : upload.status === "PARTIAL"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-red-100 text-red-800"
                        }`}
                      >
                        {upload.status}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-gray-700">{upload.total_rows?.toLocaleString() || 0}</td>
                    <td className="py-3 px-3 text-gray-700">{upload.processed_rows?.toLocaleString() || 0}</td>
                    <td className="py-3 px-3 text-gray-500 text-xs">
                      {upload.created_at ? new Date(upload.created_at).toLocaleString() : "N/A"}
                    </td>
                    <td className="py-3 px-3">
                      <a
                        href={getFailedRowsDownloadUrl(upload.id)}
                        className="text-xs text-blue-600 hover:text-blue-800 font-medium underline"
                        title="Download failed rows if any"
                      >
                        Failed Rows
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}