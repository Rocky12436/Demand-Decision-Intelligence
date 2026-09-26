import React, { useEffect, useState, useMemo } from "react";
import {
  Upload,
  UploadCloud,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  Trash2,
  Loader2,
  RefreshCw,
  Info,
  Check,
  X,
  FileCheck,
  ArrowRight,
  ShieldCheck,
  Calendar,
  Layers,
  HelpCircle,
} from "lucide-react";
import {
  uploadSalesFile,
  getUploads,
  resolveSkus,
  getProducts,
  getFailedRowsDownloadUrl,
  deleteUploadJob,
  getUploadJobStatus,
} from "../../services/api";
import {
  PageShell,
  PageHeader,
  Card,
  StatCard,
  StatusBadge,
  DataTable,
  EmptyState,
  SegmentedControl,
} from "../../components/ui";

export default function UploadPage() {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [jobProgress, setJobProgress] = useState(null);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");
  const [uploads, setUploads] = useState([]);
  const [products, setProducts] = useState([]);
  const [skuSelections, setSkuSelections] = useState({});
  const [resolving, setResolving] = useState(false);
  const [resolveSuccessMsg, setResolveSuccessMsg] = useState("");
  const [conflictMode, setConflictMode] = useState("REPLACE");
  const [allowDuplicate, setAllowDuplicate] = useState(false);
  const [duplicateConflict, setDuplicateConflict] = useState(null);
  const [deletingId, setDeletingId] = useState(null);
  const [dragActive, setDragActive] = useState(false);

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

  const handleFile = (selectedFile) => {
    setError("");
    setResult(null);
    setResolveSuccessMsg("");

    if (!selectedFile) {
      setFile(null);
      return;
    }

    if (!selectedFile.name.toLowerCase().endsWith(".csv")) {
      setError("Please select a valid CSV spreadsheet file (.csv).");
      setFile(null);
      return;
    }

    setFile(selectedFile);
  };

  const handleFileChange = (event) => {
    const selectedFile = event.target.files[0];
    handleFile(selectedFile);
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFile(e.dataTransfer.files[0]);
    }
  };

  const downloadSampleTemplate = () => {
    const csvContent =
      "date_,city_name,order_id,cart_id,dim_customer_key,procured_quantity,unit_selling_price,total_discount_amount,product_id,total_weighted_landing_price\n" +
      "2026-04-01,Delhi,ORD101,CRT101,CUST101,10,150.00,15.00,19512,120.00\n" +
      "2026-04-01,Bengaluru,ORD102,CRT102,CUST102,5,245.00,20.00,391306,190.00\n" +
      "2026-04-02,Mumbai,ORD103,CRT103,CUST103,12,28.00,0.00,12872,22.00\n";

    const blob = new Blob([csvContent], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.setAttribute("href", url);
    link.setAttribute("download", "sample_sales_template.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleUpload = async () => {
    if (!file) {
      setError("Please select a sales CSV spreadsheet first.");
      return;
    }

    try {
      setUploading(true);
      setError("");
      setResult(null);
      setJobProgress(null);
      setDuplicateConflict(null);
      setResolveSuccessMsg("");

      const data = await uploadSalesFile(file, {
        conflict_mode: conflictMode,
        allow_duplicate: allowDuplicate,
      });

      if (data && data.isConflict) {
        setDuplicateConflict(data);
        setUploading(false);
      } else if (data && (data.status === "pending" || data.poll_url)) {
        const jobId = data.job_id || data.upload_id;
        setJobProgress({
          job_id: jobId,
          status: "pending",
          current_stage: "parsing",
          progress_pct: 10,
        });

        const pollInterval = setInterval(async () => {
          try {
            const statusData = await getUploadJobStatus(jobId);
            setJobProgress({
              job_id: jobId,
              status: statusData.status,
              current_stage: statusData.current_stage || "processing",
              progress_pct: statusData.progress_pct || 0,
            });

            if (["COMPLETED", "PARTIAL", "REJECTED", "FAILED"].includes(statusData.status)) {
              clearInterval(pollInterval);
              setJobProgress(null);
              setResult(statusData);
              await loadUploads();
              setFile(null);
              setUploading(false);
            }
          } catch (pollErr) {
            clearInterval(pollInterval);
            setJobProgress(null);
            setError(`Status polling failed: ${pollErr.message}`);
            setUploading(false);
          }
        }, 2000);
      } else {
        setResult(data);
        await loadUploads();
        setFile(null);
        setUploading(false);
      }
    } catch (err) {
      setError(err.message || "Upload failed");
      setUploading(false);
    }
  };

  const handleDeleteUpload = async (uploadId) => {
    if (!window.confirm(`Delete Upload #${uploadId}? This will remove all imported sales data from this file and may affect forecasts.`)) {
      return;
    }

    try {
      setDeletingId(uploadId);
      setError("");
      await deleteUploadJob(uploadId);
      setResolveSuccessMsg(`Upload #${uploadId} successfully deleted.`);
      await loadUploads();
    } catch (err) {
      setError(err.message || `Failed to delete upload #${uploadId}`);
    } finally {
      setDeletingId(null);
    }
  };

  // Determine state: SUCCESS (green), PARTIAL (amber), REJECTED (red)
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

  const stats = useMemo(() => {
    if (!result) return null;
    const total = Number(result.total_rows || 0);
    const valid = Number(result.valid_rows || 0);
    const invalid = Number(result.invalid_rows || (total ? total - valid : 0));
    const unmappedCount = Array.isArray(result.unmapped_skus) ? result.unmapped_skus.length : 0;
    const validPct = total > 0 ? Math.round((valid / total) * 100) : 0;

    return { total, valid, invalid, unmappedCount, validPct };
  }, [result]);

  const handleResolveSkus = async () => {
    if (!result || !result.upload_id) return;

    const mappings = Object.entries(skuSelections)
      .filter(([_, masterId]) => masterId && String(masterId).trim() !== "")
      .map(([rawSku, masterId]) => ({
        raw_sku: rawSku,
        product_id: String(masterId).trim(),
      }));

    if (mappings.length === 0) {
      setError("Please select at least one master product to map.");
      return;
    }

    try {
      setResolving(true);
      setError("");
      setResolveSuccessMsg("");
      const res = await resolveSkus(result.upload_id, mappings);

      setResolveSuccessMsg(
        `Successfully linked ${res.resolved_count || mappings.length} SKU(s). Reprocessed rows were updated.`
      );

      // Remove newly mapped SKUs from the current unmapped list in state
      const mappedSkusSet = new Set(mappings.map((m) => m.raw_sku));
      setResult((prev) => ({
        ...prev,
        unmapped_skus: (prev.unmapped_skus || []).filter((item) => {
          const sku = typeof item === "string" ? item : item.sku;
          return !mappedSkusSet.has(sku);
        }),
      }));
      await loadUploads();
    } catch (err) {
      setError(err.message || "Failed to resolve SKU mappings");
    } finally {
      setResolving(false);
    }
  };

  return (
    <PageShell maxWidth="1400px">
      <PageHeader
        icon={UploadCloud}
        title="Upload Sales Sheet"
        subtitle="Upload your store's daily sales spreadsheet (CSV). The system automatically checks every item, updates your inventory, and tells you what to reorder today."
        actions={
          <button onClick={downloadSampleTemplate} className="diq-btn diq-btn-secondary">
            <Download size={14} /> Download Sample Template
          </button>
        }
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
        {/* ── Error Banner ── */}
        {error && (
          <div style={{
            backgroundColor: 'var(--status-critical-bg)',
            border: '1px solid var(--status-critical-border)',
            borderRadius: 'var(--border-radius-md)',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            color: 'var(--status-critical-text)',
            fontSize: '13px',
          }}>
            <XCircle size={18} style={{ flexShrink: 0 }} />
            <div style={{ flex: 1 }}>{error}</div>
            <button
              onClick={() => setError("")}
              style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', padding: 4 }}
            >
              <X size={14} />
            </button>
          </div>
        )}

        {/* ── Duplicate Conflict Resolution Card ── */}
        {duplicateConflict && (
          <div style={{
            backgroundColor: 'var(--status-warning-bg)',
            border: '1px solid var(--status-warning-border)',
            borderRadius: 'var(--border-radius-md)',
            padding: '16px 20px',
            color: 'var(--text-primary)',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
              <AlertTriangle size={18} style={{ color: 'var(--status-warning-text)' }} />
              <strong style={{ fontSize: '14px' }}>Duplicate File Detected</strong>
            </div>
            <p style={{ fontSize: '13px', color: 'var(--text-secondary)', marginBottom: '14px' }}>
              This exact CSV file was already uploaded in <strong>Job #{duplicateConflict.prior_job_id}</strong>.
              Would you like to import it again?
            </p>
            <div style={{ display: 'flex', gap: '10px' }}>
              <button
                onClick={() => {
                  setAllowDuplicate(true);
                  setDuplicateConflict(null);
                  setTimeout(() => handleUpload(), 50);
                }}
                className="diq-btn diq-btn-primary diq-btn-sm"
              >
                Upload Anyway
              </button>
              <button
                onClick={() => {
                  setDuplicateConflict(null);
                  setFile(null);
                }}
                className="diq-btn diq-btn-secondary diq-btn-sm"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* ── Success Banner ── */}
        {resolveSuccessMsg && (
          <div style={{
            backgroundColor: 'var(--status-success-bg)',
            border: '1px solid var(--status-success-border)',
            borderRadius: 'var(--border-radius-md)',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
            color: 'var(--status-success-text)',
            fontSize: '13px',
          }}>
            <CheckCircle2 size={18} style={{ flexShrink: 0 }} />
            <div>{resolveSuccessMsg}</div>
          </div>
        )}

        {/* ── Upload Area Card ── */}
        <Card title="Upload Sales Spreadsheet" icon={FileSpreadsheet}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
            {/* Drag & Drop Zone */}
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              style={{
                border: dragActive ? '2px dashed var(--accent-primary)' : '2px dashed var(--border-subtle)',
                borderRadius: 'var(--border-radius-lg)',
                padding: '36px 20px',
                textAlign: 'center',
                backgroundColor: dragActive ? 'var(--bg-surface-hover)' : 'var(--bg-surface-subtle)',
                transition: 'all 0.15s ease',
                cursor: 'pointer',
              }}
            >
              <input
                type="file"
                accept=".csv"
                id="file-upload"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
              <label htmlFor="file-upload" style={{ cursor: 'pointer', display: 'block' }}>
                {file ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}>
                    <div style={{
                      width: '40px', height: '40px', borderRadius: '50%',
                      backgroundColor: 'var(--status-success-bg)',
                      display: 'flex', alignItems: 'center', justifyContent: 'center',
                      color: 'var(--status-success-text)',
                    }}>
                      <Check size={20} />
                    </div>
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '15px' }}>{file.name}</span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      {(file.size / 1024).toFixed(1)} KB — Ready to upload
                    </span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                    <UploadCloud size={32} style={{ color: 'var(--accent-primary)', marginBottom: '4px' }} />
                    <span style={{ fontWeight: 500, color: 'var(--text-primary)', fontSize: '14px' }}>
                      Drag and drop your sales CSV here, or click to browse
                    </span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                      Supports standard comma-separated sales exports up to 100MB
                    </span>
                  </div>
                )}
              </label>
            </div>

            <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '14px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>
                  When data overlaps:
                </span>
                <SegmentedControl
                  size="sm"
                  value={conflictMode}
                  onChange={setConflictMode}
                  options={[
                    { value: "REPLACE", label: "Replace existing dates" },
                    { value: "APPEND", label: "Add to existing" },
                    { value: "UPSERT", label: "Update duplicates" },
                  ]}
                />
              </div>

              <button
                onClick={handleUpload}
                disabled={!file || uploading}
                className="diq-btn diq-btn-primary"
                style={{ padding: '10px 24px', fontSize: '14px', opacity: (!file || uploading) ? 0.5 : 1 }}
              >
                {uploading ? (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Loader2 size={16} style={{ animation: 'spin 1s linear infinite' }} />
                    Processing...
                  </span>
                ) : (
                  <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                    <Upload size={16} />
                    Upload & Validate
                  </span>
                )}
              </button>
            </div>
          </div>
        </Card>

        {/* ── Async Job Polling Progress ── */}
        {jobProgress && (
          <Card title="Ingestion in Progress" icon={RefreshCw}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '13px' }}>
              <span style={{ color: 'var(--text-secondary)' }}>
                Stage: <strong>{jobProgress.current_stage || "Processing"}</strong>
              </span>
              <span style={{ fontWeight: 600, color: 'var(--accent-primary)' }}>
                {jobProgress.progress_pct || 10}%
              </span>
            </div>
            <div style={{ height: '6px', borderRadius: '3px', backgroundColor: 'var(--bg-surface-subtle)', overflow: 'hidden' }}>
              <div style={{
                height: '100%',
                width: `${jobProgress.progress_pct || 10}%`,
                backgroundColor: 'var(--accent-primary)',
                transition: 'width 0.3s ease',
              }} />
            </div>
          </Card>
        )}

        {/* ── Upload Results Card ── */}
        {result && stats && (
          <Card
            style={{
              borderColor: uploadState === 'SUCCESS' ? 'var(--status-success-border)' :
                           uploadState === 'PARTIAL' ? 'var(--status-warning-border)' : 'var(--status-critical-border)',
            }}
          >
            {/* Header */}
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'center',
              paddingBottom: '16px', borderBottom: '1px solid var(--border-subtle)',
              flexWrap: 'wrap', gap: '12px',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <div style={{
                  width: '40px', height: '40px', borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  backgroundColor: uploadState === 'SUCCESS' ? 'var(--status-success-bg)' :
                                   uploadState === 'PARTIAL' ? 'var(--status-warning-bg)' : 'var(--status-critical-bg)',
                  color: uploadState === 'SUCCESS' ? 'var(--status-success-text)' :
                         uploadState === 'PARTIAL' ? 'var(--status-warning-text)' : 'var(--status-critical-text)',
                }}>
                  {uploadState === 'SUCCESS' ? <CheckCircle2 size={22} /> :
                   uploadState === 'PARTIAL' ? <AlertTriangle size={22} /> : <XCircle size={22} />}
                </div>
                <div>
                  <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>
                    {uploadState === 'SUCCESS' ? 'All Rows Validated & Imported' :
                     uploadState === 'PARTIAL' ? 'Partially Imported with Warnings' : 'Upload Rejected'}
                  </h3>
                  <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                    Job #{result.upload_id || result.job_id || '—'}
                  </span>
                </div>
              </div>

              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                {stats.invalid > 0 && result.upload_id && (
                  <a
                    href={getFailedRowsDownloadUrl(result.upload_id)}
                    className="diq-btn diq-btn-secondary diq-btn-sm"
                    download
                  >
                    <Download size={14} /> Download {stats.invalid} Failed Rows
                  </a>
                )}
                <StatusBadge
                  variant={uploadState === 'SUCCESS' ? 'success' : uploadState === 'PARTIAL' ? 'warning' : 'critical'}
                  label={result.status || uploadState}
                />
              </div>
            </div>

            {/* KPI Stats */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginTop: '16px' }}>
              <StatCard label="Total Rows" value={stats.total.toLocaleString()} />
              <StatCard label="Accepted Rows" value={stats.valid.toLocaleString()} subtext={`${stats.validPct}% valid`} />
              <StatCard
                label="Rejected Rows"
                value={stats.invalid.toLocaleString()}
                style={stats.invalid > 0 ? { borderColor: 'var(--status-critical-border)' } : {}}
              />
              <StatCard label="Unmapped SKUs" value={stats.unmappedCount} />
            </div>

            {/* Unmapped SKU Resolution UI */}
            {stats.unmappedCount > 0 && (
              <div style={{
                marginTop: '20px', padding: '16px',
                borderRadius: 'var(--border-radius-md)',
                backgroundColor: 'var(--bg-surface-subtle)',
                border: '1px solid var(--border-subtle)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <div>
                    <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 600 }}>Unmapped Products Detected</h4>
                    <p style={{ margin: '2px 0 0 0', fontSize: '12px', color: 'var(--text-secondary)' }}>
                      Match raw incoming SKU identifiers with verified master products to include them in forecasting.
                    </p>
                  </div>
                  <button
                    onClick={handleResolveSkus}
                    disabled={resolving}
                    className="diq-btn diq-btn-primary diq-btn-sm"
                  >
                    {resolving ? 'Saving Mappings...' : 'Apply Mappings'}
                  </button>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: '10px' }}>
                  {result.unmapped_skus.map((item, idx) => {
                    const rawSku = typeof item === "string" ? item : item.sku;
                    const suggestion = typeof item === "object" ? item.suggested_mapping : null;

                    return (
                      <div key={idx} style={{
                        padding: '10px 12px', borderRadius: '6px',
                        backgroundColor: 'var(--bg-surface)', border: '1px solid var(--border-subtle)',
                        fontSize: '12px',
                      }}>
                        <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: '6px' }}>
                          SKU: {rawSku}
                        </div>
                        <select
                          value={skuSelections[rawSku] || ""}
                          onChange={(e) => setSkuSelections({ ...skuSelections, [rawSku]: e.target.value })}
                          style={{
                            width: '100%', padding: '6px 8px', borderRadius: '4px',
                            border: '1px solid var(--border-strong)', fontSize: '12px',
                            backgroundColor: '#ffffff', color: 'var(--text-primary)',
                          }}
                        >
                          <option value="">-- Link to Master Product --</option>
                          {products.map((p) => (
                            <option key={p.product_id} value={p.product_id}>
                              #{p.product_id} - {p.product_name || `Product ${p.product_id}`}
                            </option>
                          ))}
                        </select>
                        {suggestion && (
                          <div style={{ marginTop: '4px', fontSize: '10px', color: 'var(--accent-primary)' }}>
                            Suggested: #{suggestion.product_id} ({Math.round((suggestion.confidence || 0) * 100)}% match)
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </Card>
        )}

        {/* ── Upload History ── */}
        <Card
          title="Upload History"
          icon={RefreshCw}
          actions={
            <button onClick={loadUploads} className="diq-btn diq-btn-secondary diq-btn-sm">
              <RefreshCw size={12} /> Refresh
            </button>
          }
        >
          {uploads.length === 0 ? (
            <EmptyState
              icon={FileSpreadsheet}
              title="No uploads yet"
              description="Upload your first sales CSV to begin demand intelligence analysis."
            />
          ) : (
            <DataTable
              columns={[
                { key: 'id', title: 'ID', render: (val, row) => `#${row?.id ?? val}` },
                { key: 'filename', title: 'File Name', render: (val, row) => <strong>{row?.filename ?? val}</strong> },
                {
                  key: 'status',
                  title: 'Status',
                  render: (val, row) => {
                    const st = row?.status ?? val;
                    return (
                      <StatusBadge
                        variant={
                          st === 'COMPLETED' || st === 'SUCCESS' ? 'success' :
                          st === 'PARTIAL' ? 'warning' : 'critical'
                        }
                        label={st}
                        size="sm"
                      />
                    );
                  },
                },
                {
                  key: 'processed_rows',
                  title: 'Rows Ingested',
                  render: (val, row) => `${(row?.processed_rows || 0).toLocaleString()} / ${(row?.total_rows || 0).toLocaleString()}`,
                },
                {
                  key: 'created_at',
                  title: 'Date',
                  render: (val, row) => {
                    const dateVal = row?.created_at ?? val;
                    return dateVal ? new Date(dateVal).toLocaleString('en-IN') : 'Recent';
                  },
                },
                {
                  key: 'actions',
                  title: 'Actions',
                  render: (val, row) => (
                    <button
                      onClick={() => row?.id && handleDeleteUpload(row.id)}
                      disabled={deletingId === row?.id}
                      className="diq-btn diq-btn-secondary diq-btn-sm"
                      style={{ padding: '4px 8px', color: 'var(--status-critical-text)' }}
                      title="Delete upload and its data"
                    >
                      <Trash2 size={12} /> {deletingId === row?.id ? 'Deleting...' : 'Delete'}
                    </button>
                  ),
                },
              ]}
              data={uploads}
              keyField="id"
            />
          )}
        </Card>
      </div>

      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
      `}</style>
    </PageShell>
  );
}