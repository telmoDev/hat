export function badgeText(items) {
  const total = items.reduce((sum, item) => sum + item.quantity, 0);
  if (total === 0) return "";
  return total > 99 ? "99+" : String(total);
}
