import { describe, expect, it } from "vitest";

import { redactTokens } from "./observability";

describe("redactTokens", () => {
  it.each([
    ["https://app.x/invite/abc123", "https://app.x/invite/[token]"],
    ["/reset-password/xyz?x=1", "/reset-password/[token]?x=1"],
    ["/api/v1/auth/invitations/tok_en", "/api/v1/auth/invitations/[token]"],
    ["/api/v1/auth/invitations/accept", "/api/v1/auth/invitations/accept"],
    ["/settings/members", "/settings/members"],
  ])("%s → %s", (input, expected) => {
    expect(redactTokens(input)).toBe(expected);
  });
});
