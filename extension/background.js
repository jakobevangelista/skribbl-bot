chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  if (!message || message.type !== "guess") {
    return;
  }
  fetch("http://127.0.0.1:8765/guess", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(message.body),
  })
    .then(async (response) => {
      const payload = await response.json().catch(() => ({}));
      if (!response.ok && !payload.error) {
        payload.error = `Guess server returned HTTP ${response.status}`;
      }
      sendResponse(payload);
    })
    .catch(() => {
      sendResponse({ error: "Local guess server is not running on 127.0.0.1:8765" });
    });
  return true;
});
