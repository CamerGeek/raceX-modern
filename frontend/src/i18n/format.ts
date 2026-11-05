export function interpolate(template: string, values: Record<string, string | number>): string {
  return template.replace(/\{(\w+)\}/g, (match, key: string) =>
    key in values ? String(values[key]) : match,
  );
}

export function priceLabel(value: number, intlLocale: string): string {
  return `${new Intl.NumberFormat(intlLocale, { maximumFractionDigits: 0 }).format(value)} FCFA`;
}
