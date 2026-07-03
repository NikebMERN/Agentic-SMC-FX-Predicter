export function PageAlerts({ error, notice, onClearNotice }) {
  return (
    <>
      {error && <p className="mb-3 rounded border border-[#f85149]/40 bg-[#3d1d20]/40 px-3 py-2 text-sm text-[#f85149]">{error}</p>}
      {notice && (
        <p className="mb-3 flex items-center justify-between rounded border border-[#238636]/40 bg-[#1a3a24]/40 px-3 py-2 text-sm text-[#3fb950]">
          <span>{notice}</span>
          {onClearNotice && (
            <button type="button" onClick={onClearNotice} className="text-xs text-[#8b949e] hover:text-white">
              dismiss
            </button>
          )}
        </p>
      )}
    </>
  );
}

export default PageAlerts;
