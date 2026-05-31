// GOOPHER background service worker (MV3).
// Opens the side panel when the toolbar icon is clicked. All conversational
// logic lives in the side panel; the backend does the heavy lifting.

chrome.runtime.onInstalled.addListener(() => {
  // Allow the action click to toggle the side panel.
  chrome.sidePanel
    .setPanelBehavior({ openPanelOnActionClick: true })
    .catch((err) => console.error("GOOPHER sidePanel setup failed:", err));
});

// Fallback for browsers/versions where setPanelBehavior isn't honored.
chrome.action.onClicked.addListener(async (tab) => {
  try {
    await chrome.sidePanel.open({ windowId: tab.windowId });
  } catch (err) {
    console.error("GOOPHER: unable to open side panel", err);
  }
});
