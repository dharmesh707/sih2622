export default function StatusPill({ children, tone = 'teal' }) {
  return <span className={`status-pill ${tone}`}>{children}</span>;
}
