import { useEffect, useRef, useState } from "react";
import client, { BASE_URL, apiErrorMessage } from "../api/client";
import { Button } from "./ui";
import { Paperclip, X, Upload, Eye, FileText, Loader2, Trash2 } from "lucide-react";

/**
 * Attach & preview documents (invoices/bills, payment receipts, employee
 * proof screenshots) against any entity. Pass exactly one of expenseId /
 * invoiceId / paymentId / claimId / claimLineId, matching `documentType`.
 */
export default function Attachments({
  documentType, expenseId, invoiceId, paymentId, claimId, claimLineId,
  label = "Attachments", compact = false, readOnly = false,
}) {
  const [open, setOpen] = useState(false);
  const [docs, setDocs] = useState([]);
  const [loading, setLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  const [previewDoc, setPreviewDoc] = useState(null);
  const [pendingFile, setPendingFile] = useState(null);
  const fileInputRef = useRef(null);

  const entityParams = { expense_id: expenseId, invoice_id: invoiceId, payment_id: paymentId, claim_id: claimId, claim_line_id: claimLineId };

  function load() {
    setLoading(true);
    client.get("/documents/by-entity", { params: entityParams })
      .then((res) => setDocs(res.data))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (open) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  function handleFileSelected(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError("");
    setPendingFile(file);
  }

  function clearPendingFile() {
    setPendingFile(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  }

  async function deleteDoc(doc) {
    if (!window.confirm(`Remove "${doc.original_filename}"?`)) return;
    setError("");
    try {
      await client.delete(`/documents/${doc.id}`);
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    }
  }

  async function confirmUpload() {
    if (!pendingFile) return;
    setUploading(true);
    setError("");
    try {
      const form = new FormData();
      form.append("document_type", documentType);
      Object.entries(entityParams).forEach(([k, v]) => { if (v) form.append(k, v); });
      form.append("file", pendingFile);
      await client.post("/documents", form, { headers: { "Content-Type": "multipart/form-data" } });
      clearPendingFile();
      load();
    } catch (err) {
      setError(apiErrorMessage(err));
    } finally {
      setUploading(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); setOpen(true); }}
        className={`relative inline-flex items-center gap-1.5 text-xs font-medium rounded-md border border-ink/15 hover:bg-brand-50 ${compact ? "px-2 py-1" : "px-2.5 py-1.5"}`}
      >
        <Paperclip size={13} /> {label}
        {docs.length > 0 && (
          <span className="inline-flex items-center justify-center min-w-[16px] h-4 px-1 rounded-full bg-accent-500 text-white text-[10px] font-semibold leading-none tabular">
            {docs.length}
          </span>
        )}
      </button>

      {open && (
        <div className="fixed inset-0 bg-ink/40 z-40 flex items-center justify-center p-4" onClick={() => { setOpen(false); clearPendingFile(); setError(""); }}>
          <div className="bg-white rounded-lg shadow-xl w-full max-w-md p-5 relative" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => { setOpen(false); clearPendingFile(); setError(""); }} className="absolute top-4 right-4 text-ink/40 hover:text-ink"><X size={18} /></button>
            <h3 className="font-display font-semibold text-lg mb-1">Attachments</h3>
            <p className="text-xs text-ink/50 mb-4">Invoice/bill copies, payment receipts, or proof of expense (PDF, JPG, PNG, WEBP — up to 15MB).</p>

            {loading ? (
              <div className="flex items-center gap-2 text-sm text-ink/40 py-4"><Loader2 size={14} className="animate-spin" /> Loading…</div>
            ) : docs.length === 0 ? (
              <div className="text-sm text-ink/40 py-3">No documents attached yet.</div>
            ) : (
              <ul className="space-y-2 mb-4">
                {docs.map((d) => (
                  <li key={d.id} className="flex items-center gap-2 bg-brand-50 rounded-md px-3 py-2">
                    <FileText size={15} className="text-ink/40 shrink-0" />
                    <span className="text-sm truncate flex-1" title={d.original_filename}>{d.original_filename}</span>
                    <span className="text-[11px] text-ink/40 shrink-0">{(d.file_size / 1024).toFixed(0)} KB</span>
                    <button type="button" onClick={() => setPreviewDoc(d)} className="text-brand-700 hover:text-brand-900 shrink-0" title="Preview">
                      <Eye size={16} />
                    </button>
                    {!readOnly && (
                      <button type="button" onClick={() => deleteDoc(d)} className="text-ink/30 hover:text-danger shrink-0" title="Remove">
                        <Trash2 size={15} />
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}

            {error && <div className="text-sm text-danger bg-danger/10 rounded-md px-3 py-2 mb-3">{error}</div>}

            {readOnly ? null : pendingFile ? (
              <div className="border border-brand-200 bg-brand-50 rounded-md p-3 space-y-3">
                <div className="flex items-center gap-2">
                  <FileText size={15} className="text-brand-700 shrink-0" />
                  <span className="text-sm truncate flex-1" title={pendingFile.name}>{pendingFile.name}</span>
                  <span className="text-[11px] text-ink/40 shrink-0">{(pendingFile.size / 1024).toFixed(0)} KB</span>
                </div>
                <div className="flex gap-2">
                  <Button type="button" disabled={uploading} onClick={confirmUpload} className="flex-1">
                    {uploading ? <><Loader2 size={14} className="animate-spin" /> Uploading…</> : <><Upload size={14} /> Upload this file</>}
                  </Button>
                  <Button type="button" variant="ghost" disabled={uploading} onClick={clearPendingFile}>Cancel</Button>
                </div>
              </div>
            ) : (
              <label>
                <input ref={fileInputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,.xlsx,.csv" className="hidden" onChange={handleFileSelected} />
                <Button type="button" variant="outline" onClick={() => fileInputRef.current?.click()} className="w-full">
                  <Paperclip size={14} /> Choose a file to attach
                </Button>
              </label>
            )}
          </div>
        </div>
      )}

      {previewDoc && <PreviewModal doc={previewDoc} onClose={() => setPreviewDoc(null)} />}
    </>
  );
}

function PreviewModal({ doc, onClose }) {
  const [blobUrl, setBlobUrl] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let revoke;
    client.get(`/documents/${doc.id}/download`, { responseType: "blob" })
      .then((res) => {
        const url = URL.createObjectURL(res.data);
        revoke = url;
        setBlobUrl(url);
      })
      .catch(() => setError("Could not load this file."));
    return () => { if (revoke) URL.revokeObjectURL(revoke); };
  }, [doc.id]);

  const isPdf = doc.mime_type === "application/pdf";
  const isImage = doc.mime_type?.startsWith("image/");

  return (
    <div className="fixed inset-0 bg-ink/70 z-50 flex items-center justify-center p-4" onClick={onClose}>
      <div className="bg-white rounded-lg shadow-2xl w-full max-w-3xl h-[85vh] flex flex-col" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 py-3 border-b border-ink/10">
          <span className="text-sm font-medium truncate">{doc.original_filename}</span>
          <div className="flex items-center gap-3">
            {blobUrl && (
              <a href={blobUrl} download={doc.original_filename} className="text-xs text-brand-700 hover:underline">Download</a>
            )}
            <button onClick={onClose} className="text-ink/40 hover:text-ink"><X size={18} /></button>
          </div>
        </div>
        <div className="flex-1 overflow-auto bg-ink/5 flex items-center justify-center">
          {error && <div className="text-sm text-danger">{error}</div>}
          {!error && !blobUrl && <Loader2 size={20} className="animate-spin text-ink/30" />}
          {blobUrl && isPdf && <iframe src={blobUrl} title={doc.original_filename} className="w-full h-full border-0" />}
          {blobUrl && isImage && <img src={blobUrl} alt={doc.original_filename} className="max-w-full max-h-full object-contain" />}
          {blobUrl && !isPdf && !isImage && (
            <div className="text-sm text-ink/50">Preview not available for this file type — use Download instead.</div>
          )}
        </div>
      </div>
    </div>
  );
}
