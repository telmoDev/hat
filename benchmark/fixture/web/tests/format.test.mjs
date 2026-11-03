import { test } from "node:test";
import assert from "node:assert/strict";
import { formatPrice } from "../src/format.mjs";
import { productList } from "../src/main.mjs";

test("formats cents as dollars", () => {
  assert.equal(formatPrice(150), "$1.50");
  assert.equal(formatPrice(2500), "$25.00");
});

test("lists products", () => {
  assert.equal(productList([{ name: "Pen", price_cents: 150 }]), "<p>Pen: $1.50</p>");
});
