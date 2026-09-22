export default function MetricStrip({ metrics }) {
  return (
    <div className="metric-strip">
      {metrics.map((metric) => (
        <div key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}
