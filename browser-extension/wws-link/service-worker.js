chrome.runtime.onMessageExternal.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "GET_REWARDS_TOKEN") return;
  getRewardsToken().then(sendResponse);
  return true;
});

async function getRewardsToken() {
  try {
    const tabs = await chrome.tabs.query({
      url: "https://www.everyday.com.au/*",
    });
    for (const tab of tabs) {
      if (tab.id == null) continue;
      try {
        const result = await chrome.tabs.sendMessage(tab.id, {
          type: "READ_REWARDS_TOKEN",
        });
        if (result && typeof result.token === "string" && result.token) {
          return result;
        }
      } catch {
        // The content script may not have been injected into this tab yet.
      }
    }
    return { token: null };
  } catch (error) {
    return { token: null, error: String(error) };
  }
}
