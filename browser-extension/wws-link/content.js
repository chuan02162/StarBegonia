function readRewardsToken() {
  try {
    const raw = window.localStorage.getItem("authStatusData");
    if (!raw) return { token: null };
    const data = JSON.parse(raw);
    if (data.reason !== "AUTHENTICATED") return { token: null };
    if (data.accessTokenExpired === "Y") return { token: null };
    if (data.isTempPassword === true) return { token: null };
    if (!data.access_token) return { token: null };
    return { token: data.access_token, userAgent: navigator.userAgent };
  } catch (error) {
    return { token: null, error: String(error) };
  }
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (message && message.type === "READ_REWARDS_TOKEN") {
    sendResponse(readRewardsToken());
  }
});
