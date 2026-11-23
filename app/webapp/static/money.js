/** Course money is always shown as `300 000 so'm`. */
export function money(amount) {
  const text = String(Math.round(Number(amount) || 0)).replace(/\B(?=(\d{3})+(?!\d))/g, " ");
  return `${text} so'm`;
}
