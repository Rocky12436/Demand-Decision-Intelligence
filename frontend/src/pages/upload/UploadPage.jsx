import { useEffect, useState, useMemo } from "react";
import {
  Upload,
  FileSpreadsheet,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Download,
  Trash2,
  Loader2,
  RefreshCw,
  Info,
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
        `Successfully matched products! ${res.re_ingested_rows || 0} previously failed rows were recovered.`
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
      setError(err.message || "Failed to resolve product matches");
    } finally {
      setResolving(false);
    }
  };

  // Friendly stage labels
  const stageLabels = {
    parsing: "Reading file...",
    validating: "Checking data quality...",
    ingesting: "Saving to database...",
    processing: "Processing...",
    mapping: "Matching products...",
  };

  // Upload history table columns
  const historyColumns = [
    { key: 'id', title: '#', width: '60px', render: (val) => <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--text-muted)', fontSize: '12px' }}>#{val}</span> },
    { key: 'filename', title: 'File Name', render: (val) => <span style={{ fontWeight: 500 }}>{val || '—'}</span> },
    {
      key: 'status', title: 'Status', width: '120px',
      render: (val) => {
        const s = String(val || '').toUpperCase();
        const variant = (s === 'COMPLETED' || s === 'SUCCESS') ? 'success' : s === 'PARTIAL' ? 'warning' : 'critical';
        const label = s === 'COMPLETED' ? 'Done' : s === 'SUCCESS' ? 'Done' : s === 'PARTIAL' ? 'Partial' : s === 'FAILED' ? 'Failed' : s || '—';
        return <StatusBadge variant={variant} label={label} size="sm" />;
      }
    },
    { key: 'total_rows', title: 'Total Rows', isNumeric: true, render: (val) => (val ?? 0).toLocaleString('en-IN') },
    { key: 'processed_rows', title: 'Imported', isNumeric: true, render: (val) => (val ?? 0).toLocaleString('en-IN') },
    {
      key: 'created_at', title: 'Date', width: '160px',
      render: (val) => val ? new Date(val).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'
    },
    {
      key: '_actions', title: '', width: '180px',
      render: (_, row) => (
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <a
            href={getFailedRowsDownloadUrl(row.id)}
            style={{ display: 'inline-flex', alignItems: 'center', gap: '3px', fontSize: '12px', color: 'var(--accent-primary)', fontWeight: 500, textDecoration: 'none' }}
            title="Download rows that had errors"
          >
            <Download size={13} /> Errors
          </a>
          <button
            onClick={(e) => { e.stopPropagation(); handleDeleteUpload(row.id); }}
            disabled={deletingId === row.id}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '3px',
              fontSize: '12px', color: 'var(--status-critical-text)', fontWeight: 500,
              background: 'none', border: 'none', cursor: 'pointer',
              opacity: deletingId === row.id ? 0.5 : 1,
            }}
            title="Delete this upload and remove its data"
          >
            <Trash2 size={13} /> {deletingId === row.id ? "Deleting..." : "Delete"}
          </button>
        </div>
      )
    },
  ];

  return (
    <PageShell>
      <PageHeader
        icon={Upload}
        title="Upload Sales Data"
        subtitle="Import your sales CSV file. The system checks every row for errors before saving."
      />

      <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>

        {/* ── Upload Input Card ── */}
        <Card title="Select File" icon={FileSpreadsheet} subtitle="Choose a CSV file from your computer with sales transaction data.">

          {/* Duplicate file warning */}
          {duplicateConflict && (
            <div style={{
              marginBottom: '16px', padding: '12px 16px', borderRadius: 'var(--border-radius-md)',
              backgroundColor: 'var(--status-warning-bg)', border: '1px solid var(--status-warning-border)',
              fontSize: '13px', color: 'var(--status-warning-text)',
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontWeight: 600, marginBottom: '4px' }}>
                <AlertTriangle size={16} /> This file was already uploaded
              </div>
              <p style={{ margin: '0 0 8px 0' }}>
                The same file was previously uploaded as Job #{duplicateConflict.existing_job_id}.
              </p>
              <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', cursor: 'pointer', fontWeight: 500 }}>
                <input
                  type="checkbox"
                  checked={allowDuplicate}
                  onChange={(e) => setAllowDuplicate(e.target.checked)}
                  style={{ accentColor: 'var(--accent-primary)' }}
                />
                Upload again anyway
              </label>
            </div>
          )}

          {/* File input + upload button */}
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center', flexWrap: 'wrap' }}>
            <div style={{ flex: '1 1 300px' }}>
              <input
                type="file"
                accept=".csv"
                onChange={handleFileChange}
                id="csv-upload-input"
                style={{ display: 'none' }}
              />
              <label
                htmlFor="csv-upload-input"
                style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px',
                  padding: '32px 20px', border: '2px dashed var(--border-strong)',
                  borderRadius: 'var(--border-radius-lg)', cursor: 'pointer',
                  backgroundColor: file ? 'var(--status-info-bg)' : 'var(--bg-surface-subtle)',
                  borderColor: file ? 'var(--accent-primary)' : 'var(--border-strong)',
                  transition: 'all 0.15s ease', textAlign: 'center',
                }}
              >
                {file ? (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                    <FileSpreadsheet size={24} style={{ color: 'var(--accent-primary)' }} />
                    <span style={{ fontWeight: 600, color: 'var(--text-primary)', fontSize: '14px' }}>{file.name}</span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>{(file.size / 1024).toFixed(1)} KB — Click to change</span>
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' }}>
                    <Upload size={24} style={{ color: 'var(--text-muted)' }} />
                    <span style={{ fontWeight: 500, color: 'var(--text-secondary)', fontSize: '14px' }}>Click to select a CSV file</span>
                    <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>or drag and drop here</span>
                  </div>
                )}
              </label>
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

          {/* Upload mode selector */}
          <div style={{
            marginTop: '16px', paddingTop: '12px', borderTop: '1px solid var(--border-subtle)',
            display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px',
          }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <span style={{ fontSize: '12px', fontWeight: 600, color: 'var(--text-secondary)' }}>When data overlaps:</span>
              <SegmentedControl
                size="sm"
                value={conflictMode}
                onChange={setConflictMode}
                options={[
                  { value: 'REPLACE', label: 'Replace old data' },
                  { value: 'ACCUMULATE', label: 'Add to existing' },
                ]}
              />
            </div>

            <label style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: 'var(--text-secondary)', cursor: 'pointer' }}>
              <input
                type="checkbox"
                checked={allowDuplicate}
                onChange={(e) => setAllowDuplicate(e.target.checked)}
                style={{ accentColor: 'var(--accent-primary)' }}
              />
              Allow re-uploading the same file
            </label>
          </div>

          {/* Error message */}
          {error && (
            <div style={{
              marginTop: '12px', padding: '10px 14px', borderRadius: 'var(--border-radius-md)',
              backgroundColor: 'var(--status-critical-bg)', border: '1px solid var(--status-critical-border)',
              color: 'var(--status-critical-text)', fontSize: '13px',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}>
              <XCircle size={16} style={{ flexShrink: 0 }} /> {error}
            </div>
          )}

          {/* Success message */}
          {resolveSuccessMsg && (
            <div style={{
              marginTop: '12px', padding: '10px 14px', borderRadius: 'var(--border-radius-md)',
              backgroundColor: 'var(--status-success-bg)', border: '1px solid var(--status-success-border)',
              color: 'var(--status-success-text)', fontSize: '13px',
              display: 'flex', alignItems: 'center', gap: '6px',
            }}>
              <CheckCircle2 size={16} style={{ flexShrink: 0 }} /> {resolveSuccessMsg}
            </div>
          )}
        </Card>

        {/* ── Processing Progress ── */}
        {jobProgress && (
          <Card style={{ borderColor: 'var(--accent-primary-border)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <div style={{
                  width: '8px', height: '8px', borderRadius: '50%', backgroundColor: 'var(--accent-primary)',
                  animation: 'pulse 2s infinite',
                }} />
                <div>
                  <div style={{ fontWeight: 600, fontSize: '15px', color: 'var(--text-primary)' }}>
                    Processing your file...
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    {stageLabels[jobProgress.current_stage] || 'Working on it...'}
                  </div>
                </div>
              </div>
              <StatusBadge variant="info" label={`Job #${jobProgress.job_id}`} size="sm" />
            </div>

            {/* Progress bar */}
            <div style={{
              width: '100%', height: '6px', backgroundColor: 'var(--bg-surface-subtle)',
              borderRadius: '3px', overflow: 'hidden',
            }}>
              <div style={{
                height: '100%', width: `${Math.max(5, jobProgress.progress_pct || 0)}%`,
                backgroundColor: 'var(--accent-primary)', borderRadius: '3px',
                transition: 'width 0.5s ease-out',
              }} />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '6px', fontSize: '12px', fontWeight: 600, color: 'var(--accent-primary)' }}>
              {jobProgress.progress_pct || 0}% complete
            </div>
          </Card>
        )}

        {/* ── Upload Results ── */}
        {result && stats && (
          <Card
            style={{
              borderColor: uploadState === 'SUCCESS' ? 'var(--status-success-border)' :
                           uploadState === 'PARTIAL' ? 'var(--status-warning-border)' : 'var(--status-critical-border)',
            }}
          >
            {/* Result Header */}
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
                  color: uploadState === 'SUCCESS' ? 'var(--status-success-icon)' :
                         uploadState === 'PARTIAL' ? 'var(--status-warning-icon)' : 'var(--status-critical-icon)',
                }}>
                  {uploadState === 'SUCCESS' && <CheckCircle2 size={22} />}
                  {uploadState === 'PARTIAL' && <AlertTriangle size={22} />}
                  {uploadState === 'REJECTED' && <XCircle size={22} />}
                </div>
                <div>
                  <div style={{ fontSize: '17px', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {uploadState === 'SUCCESS' && 'All rows imported successfully'}
                    {uploadState === 'PARTIAL' && 'Some rows had errors'}
                    {uploadState === 'REJECTED' && 'Upload failed — no rows imported'}
                  </div>
                  <div style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    Job #{result.upload_id || result.id || 'N/A'} • {result.filename || 'Uploaded file'}
                  </div>
                </div>
              </div>

              {stats.errors > 0 && result.upload_id && (
                <a
                  href={getFailedRowsDownloadUrl(result.upload_id)}
                  download={`failed_rows_${result.upload_id}.csv`}
                  className="diq-btn diq-btn-secondary diq-btn-sm"
                  style={{ textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                >
                  <Download size={14} /> Download error rows ({stats.errors.toLocaleString('en-IN')})
                </a>
              )}
            </div>

            {/* Stats Row */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px', marginTop: '16px' }}>
              <StatCard label="Total Rows" value={stats.total.toLocaleString('en-IN')} />
              <StatCard label="Imported" value={stats.valid.toLocaleString('en-IN')} subtext="Saved to database" />
              <StatCard label="Errors" value={stats.errors.toLocaleString('en-IN')} subtext="Could not be saved" />
              <StatCard label="Success Rate" value={`${stats.percentAccepted}%`} />
            </div>

            {/* Error Breakdown */}
            {sortedErrorBreakdown.length > 0 && (
              <div style={{
                marginTop: '20px', padding: '16px', backgroundColor: 'var(--bg-surface-subtle)',
                borderRadius: 'var(--border-radius-lg)', border: '1px solid var(--border-subtle)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
                  <span style={{ fontSize: '13px', fontWeight: 700, color: 'var(--text-primary)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Error Details
                  </span>
                  <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>Sorted by most common first</span>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
                  {sortedErrorBreakdown.map(([category, count]) => {
                    const pct = stats.errors > 0 ? ((count / stats.errors) * 100).toFixed(1) : 0;
                    // Convert category to plain English
                    const readableCategory = category
                      .replace(/_/g, ' ')
                      .replace(/\b\w/g, l => l.toUpperCase());
                    return (
                      <div key={category}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px', fontSize: '12px' }}>
                          <span style={{ fontWeight: 500, color: 'var(--text-primary)' }}>{readableCategory}</span>
                          <span style={{ color: 'var(--text-muted)' }}>{count.toLocaleString('en-IN')} rows ({pct}%)</span>
                        </div>
                        <div style={{ width: '100%', height: '4px', backgroundColor: '#e2e8f0', borderRadius: '2px', overflow: 'hidden' }}>
                          <div style={{
                            width: `${pct}%`, height: '100%', backgroundColor: 'var(--status-critical-icon)',
                            borderRadius: '2px', transition: 'width 0.3s ease',
                          }} />
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* SKU Mapping Panel */}
            {result.unmapped_skus && result.unmapped_skus.length > 0 && (
              <div style={{
                marginTop: '20px', padding: '16px',
                borderRadius: 'var(--border-radius-lg)',
                border: '1px solid var(--status-warning-border)',
                backgroundColor: '#ffffff',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px', flexWrap: 'wrap', gap: '12px' }}>
                  <div>
                    <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <AlertTriangle size={18} style={{ color: 'var(--status-warning-icon)' }} />
                      {result.unmapped_skus.length} unrecognised product{result.unmapped_skus.length !== 1 ? 's' : ''} found
                    </div>
                    <p style={{ fontSize: '12px', color: 'var(--text-muted)', margin: '4px 0 0' }}>
                      These product codes don't match any product in your catalogue. Match them below or create new products.
                    </p>
                  </div>

                  <div style={{ display: 'flex', gap: '6px' }}>
                    <button onClick={handleApplyAllSuggestions} className="diq-btn diq-btn-secondary diq-btn-sm">
                      Accept all suggestions
                    </button>
                    <button onClick={handleCreateAllAsNew} className="diq-btn diq-btn-secondary diq-btn-sm">
                      Create all as new
                    </button>
                  </div>
                </div>

                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '13px' }}>
                    <thead>
                      <tr style={{ borderBottom: '1px solid var(--border-subtle)', backgroundColor: 'var(--bg-surface-subtle)' }}>
                        <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>Product Code</th>
                        <th style={{ padding: '8px 12px', textAlign: 'right', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>Times Found</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>Best Match</th>
                        <th style={{ padding: '8px 12px', textAlign: 'left', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.04em', color: 'var(--text-muted)' }}>Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.unmapped_skus.map((item, idx) => {
                        const sku = typeof item === "string" ? item : item.sku;
                        const count = typeof item === "object" ? item.occurrences || 1 : 1;
                        const suggested = item.suggested_mapping?.product_id;
                        const conf = item.suggested_mapping?.confidence;

                        return (
                          <tr key={sku || idx} style={{ borderBottom: '1px solid var(--border-subtle)' }}
                              onMouseEnter={(e) => e.currentTarget.style.backgroundColor = 'var(--bg-surface-subtle)'}
                              onMouseLeave={(e) => e.currentTarget.style.backgroundColor = '#ffffff'}
                          >
                            <td style={{ padding: '10px 12px', fontFamily: 'var(--font-mono)', fontWeight: 600, color: 'var(--text-primary)' }}>
                              {sku}
                            </td>
                            <td style={{ padding: '10px 12px', textAlign: 'right', color: 'var(--text-secondary)' }} className="tabular-nums">
                              {count}
                            </td>
                            <td style={{ padding: '10px 12px' }}>
                              {suggested ? (
                                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                  <span style={{ fontWeight: 500 }}>{suggested}</span>
                                  {conf && (
                                    <StatusBadge
                                      variant={conf >= 0.75 ? 'success' : conf >= 0.5 ? 'warning' : 'neutral'}
                                      label={`${(conf * 100).toFixed(0)}% match`}
                                      size="sm"
                                    />
                                  )}
                                </div>
                              ) : (
                                <span style={{ fontSize: '12px', color: 'var(--text-disabled)', fontStyle: 'italic' }}>No match found</span>
                              )}
                            </td>
                            <td style={{ padding: '10px 12px' }}>
                              <select
                                value={skuSelections[sku] || ""}
                                onChange={(e) =>
                                  setSkuSelections((prev) => ({
                                    ...prev,
                                    [sku]: e.target.value,
                                  }))
                                }
                                style={{
                                  padding: '5px 8px', borderRadius: 'var(--border-radius-sm)',
                                  border: '1px solid var(--border-strong)', fontSize: '12px',
                                  backgroundColor: '#ffffff', color: 'var(--text-primary)',
                                  width: '100%', maxWidth: '220px',
                                }}
                              >
                                <option value="">— Choose action —</option>
                                {suggested && (
                                  <option value={suggested}>
                                    Match to: {suggested}
                                  </option>
                                )}
                                <option value="__CREATE_NEW__">
                                  + Add as new product
                                </option>
                                <optgroup label="Your Products">
                                  {products.map((p) => (
                                    <option key={p.product_id} value={p.product_id}>
                                      {p.product_id} — {p.product_name || "Unnamed"}
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

                <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '16px' }}>
                  <button
                    onClick={handleResolveSkusSubmit}
                    disabled={resolving}
                    className="diq-btn diq-btn-primary"
                    style={{ opacity: resolving ? 0.5 : 1 }}
                  >
                    {resolving ? (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> Saving matches...
                      </span>
                    ) : (
                      <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <RefreshCw size={14} /> Save matches & retry failed rows
                      </span>
                    )}
                  </button>
                </div>
              </div>
            )}
          </Card>
        )}

        {/* ── Upload History ── */}
        <Card title="Upload History" icon={FileSpreadsheet} subtitle="All previous file uploads and their results.">
          {uploads.length === 0 ? (
            <EmptyState
              icon={Upload}
              title="No uploads yet"
              description="Upload your first sales data CSV file to get started with forecasting."
            />
          ) : (
            <DataTable
              columns={historyColumns}
              data={uploads}
              keyField="id"
              emptyMessage="No upload history available."
            />
          )}
        </Card>
      </div>

      {/* Spin keyframe for loader */}
      <style>{`
        @keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }
        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
      `}</style>
    </PageShell>
  );
}