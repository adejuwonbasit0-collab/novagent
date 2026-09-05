// Minimal for now — the popup talks to the backend directly, and page
// content is read on-demand via chrome.scripting.executeScript from
// popup.js (only when the user clicks "Summarize this page"), not via an
// always-on content script. This is where a future "secure local bridge
// to desktop agent" (spec section 9) would live, so the extension can
// hand off automation/OS-level requests to the desktop agent instead of
// (or in addition to) the cloud backend.

chrome.runtime.onInstalled.addListener(() => {
  console.log("Nova extension installed");
});
