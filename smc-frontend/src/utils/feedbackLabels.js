export function outcomeLabel(feedback) {
  const labels = {
    SUCCESSFUL: "Successful",
    FAILED: "Failed",
    DID_NOT_TAKE: "Didn't take",
    UNCLEAR: "Unclear",
  };
  return labels[feedback] || feedback;
}

export function tradeEntryLabel(feedback) {
  const labels = {
    ENTERED: "Accepted — entered trade",
    DID_NOT_TAKE: "Rejected — did not take",
  };
  return labels[feedback] || feedback;
}
