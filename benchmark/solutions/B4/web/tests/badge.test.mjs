import { test } from "node:test";
import assert from "node:assert/strict";
import { badgeText } from "../src/badge.mjs";

test("badge text", () => {
  assert.equal(badgeText([]), "");
  assert.equal(badgeText([{ id: 1, quantity: 120 }]), "99+");
});
