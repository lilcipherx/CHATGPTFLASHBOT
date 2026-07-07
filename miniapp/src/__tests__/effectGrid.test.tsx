import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@twa-dev/sdk", () => ({
  default: {
    initDataUnsafe: { user: { language_code: "ru" } },
    ready: () => {},
    expand: () => {},
    HapticFeedback: { impactOccurred: () => {} },
  },
}));

const listEffects = vi.fn();
vi.mock("../api/client", () => ({
  api: { listEffects: (...a: unknown[]) => listEffects(...a) },
  // EffectCard resolves media paths through this; pass through in tests.
  mediaUrl: (p: string | null) => p ?? "",
}));

import { EffectGrid } from "../components/EffectGrid";

function fx(id: number, kind: string, name: string) {
  return {
    id, kind, name, author: null, category: "all",
    badge: null, is_ad: false, preview_url: null,
    recommended_model: null, price: 1,
  };
}

afterEach(() => vi.restoreAllMocks());

describe("EffectGrid out-of-order guard", () => {
  it("drops a stale response after the deps change", async () => {
    let resolveVideo!: (v: unknown) => void;
    let resolvePhoto!: (v: unknown) => void;
    const videoP = new Promise((r) => { resolveVideo = r; });
    const photoP = new Promise((r) => { resolvePhoto = r; });
    listEffects.mockImplementation((kind: string) => (kind === "video" ? videoP : photoP));

    const onPick = vi.fn();
    const { rerender } = render(<EffectGrid kind="video" onPick={onPick} />);
    // user switches segment before the first (video) request resolves
    rerender(<EffectGrid kind="photo" onPick={onPick} />);

    // newest (photo) resolves first…
    await act(async () => { resolvePhoto([fx(2, "photo", "PhotoFx")]); });
    // …then the stale (video) request resolves LATE and must be ignored
    await act(async () => { resolveVideo([fx(1, "video", "VideoFx")]); });

    expect(screen.getByText("PhotoFx")).toBeInTheDocument();
    expect(screen.queryByText("VideoFx")).not.toBeInTheDocument();
  });
});
