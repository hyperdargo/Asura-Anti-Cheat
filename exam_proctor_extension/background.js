// Background script
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'closeOtherTabs') {
    chrome.tabs.query({}, (tabs) => {
      const examTab = tabs.find(tab => tab.url.includes('/take'));
      if (examTab) {
        const tabsToClose = tabs.filter(tab => tab.id !== examTab.id && !tab.url.includes('chrome://'));
        tabsToClose.forEach(tab => {
          chrome.tabs.remove(tab.id);
        });
      }
    });
  }
});