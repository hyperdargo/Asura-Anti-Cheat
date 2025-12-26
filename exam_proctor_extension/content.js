// Content script for exam page
(function() {
  console.log('Exam Proctor Extension loaded');

  if (!document.getElementById('agent-token')) {
    console.log('Not on exam page (no agent-token element), skipping extension features');
    return;
  }

  // Create overlay for screenshot prevention
  const overlay = document.createElement('div');
  overlay.id = 'screenshotOverlay';
  overlay.style.cssText = `
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background-color: white;
    z-index: 9999;
    display: none;
    transition: opacity 0.3s ease;
  `;
  document.body.appendChild(overlay);

  // Extract and store token
  function extractToken() {
    const tokenElement = document.getElementById('agent-token');
    const attemptElement = document.querySelector('code');
    if (tokenElement && attemptElement) {
      const token = tokenElement.textContent.trim();
      const attemptId = attemptElement.textContent.trim();
      chrome.storage.local.set({ examToken: token, attemptId: attemptId });
      console.log('Token extracted:', token, attemptId);
    }
  }

  // Call on load and periodically
  extractToken();
  setInterval(extractToken, 5000);

  // Listen for Print Screen
  document.addEventListener('keydown', function(e) {
    if (e.keyCode === 44 || e.key === 'PrintScreen' || (e.ctrlKey && e.keyCode === 44) || (e.altKey && e.keyCode === 44)) {
      // Apply blur to prevent readable screenshots
      document.body.style.filter = 'blur(20px)';
      overlay.style.display = 'block';
      overlay.style.opacity = '1';
      setTimeout(() => {
        document.body.style.filter = '';
        overlay.style.opacity = '0';
        setTimeout(() => {
          overlay.style.display = 'none';
        }, 300);
      }, 3000);
    }
  });

  // Close other tabs
  chrome.runtime.sendMessage({ action: 'closeOtherTabs' });
})();