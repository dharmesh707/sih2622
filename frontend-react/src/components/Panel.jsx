export default function Panel({ children, className = '', ...props }) {
  return <section className={`panel ${className}`.trim()} {...props}>{children}</section>;
}
