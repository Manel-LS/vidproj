import { create } from "zustand";

export type LeftPanelTab = "media" | "templates" | "text" | "audio" | "ai";

interface EditorState {
  /** Which scene the properties panel is editing. */
  selectedSceneId: string | null;
  /** Playhead, in seconds on the project timeline. */
  time: number;
  playing: boolean;
  muted: boolean;
  volume: number;
  leftTab: LeftPanelTab;
  /** Panels collapse on narrow screens; these persist the user's choice. */
  leftOpen: boolean;
  rightOpen: boolean;
  /** Id of the text overlay being edited, so the Text panel and canvas agree. */
  selectedTextId: string | null;

  select: (sceneId: string | null) => void;
  selectText: (textId: string | null) => void;
  setTime: (time: number) => void;
  setPlaying: (playing: boolean) => void;
  setMuted: (muted: boolean) => void;
  setVolume: (volume: number) => void;
  setLeftTab: (tab: LeftPanelTab) => void;
  toggleLeft: () => void;
  toggleRight: () => void;
  reset: () => void;
}

export const useEditorStore = create<EditorState>((set) => ({
  selectedSceneId: null,
  time: 0,
  playing: false,
  muted: false,
  volume: 1,
  leftTab: "media",
  leftOpen: true,
  rightOpen: true,
  selectedTextId: null,

  select: (sceneId) => set({ selectedSceneId: sceneId, selectedTextId: null }),
  selectText: (textId) => set({ selectedTextId: textId }),
  setTime: (time) => set({ time }),
  setPlaying: (playing) => set({ playing }),
  setMuted: (muted) => set({ muted }),
  setVolume: (volume) => set({ volume }),
  setLeftTab: (leftTab) => set({ leftTab, leftOpen: true }),
  toggleLeft: () => set((state) => ({ leftOpen: !state.leftOpen })),
  toggleRight: () => set((state) => ({ rightOpen: !state.rightOpen })),
  reset: () =>
    set({ selectedSceneId: null, selectedTextId: null, time: 0, playing: false }),
}));
