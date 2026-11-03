import { formatPrice } from "./format.mjs";

export function productList(products) {
  return products.map((p) => `<p>${p.name}: ${formatPrice(p.price_cents)}</p>`).join("");
}

if (typeof document !== "undefined") {
  fetch("/products").then((r) => r.json()).then((products) => {
    document.getElementById("products").innerHTML = productList(products);
  });
}
