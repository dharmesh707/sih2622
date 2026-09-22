export default function Toast({ message, kind = 'error', onClose }) {
  if (!message) return null;
  return (
    <div className={`toast ${kind}`} role="alert">
      <span>{message}</span>
      <button type="button" onClick={onClose} aria-label="Dismiss">×</button>
    </div>
  );
}
