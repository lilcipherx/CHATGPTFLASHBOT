import "@testing-library/jest-dom";

// Tell React this is an act()-aware environment so component tests that wrap
// updates in act() don't emit the "not configured to support act(...)" warning.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
(globalThis as any).IS_REACT_ACT_ENVIRONMENT = true;
