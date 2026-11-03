import { test } from "node:test";
import assert from "node:assert/strict";
import { badgeText } from "../src/badge.mjs";

test("O1 empty cart", () => assert.equal(badgeText([]), ""));
test("O1 total quantity up to 99", () => {
  assert.equal(badgeText([{ id: 1, quantity: 2 }, { id: 2, quantity: 3 }]), "5");
  assert.equal(badgeText([{ id: 1, quantity: 99 }]), "99");
});
test("O2 above 99", () => assert.equal(badgeText([{ id: 1, quantity: 60 }, { id: 2, quantity: 40 }]), "99+"));
