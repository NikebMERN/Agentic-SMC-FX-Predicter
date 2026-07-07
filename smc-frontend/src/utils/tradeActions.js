export const NON_TRADE_ACTIONS = ["NO_TRADE", "WAIT_FOR_CONFIRMATION"];

export function isTradeAction(action) {
  return Boolean(action && !NON_TRADE_ACTIONS.includes(action));
}
