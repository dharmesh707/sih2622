export default function Spinner({ label = 'Working...' }) {
  return <span className="spinner-wrap"><span className="spinner" />{label}</span>;
}
