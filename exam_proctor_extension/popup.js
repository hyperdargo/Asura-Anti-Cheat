// Popup script
document.addEventListener('DOMContentLoaded', () => {
  chrome.storage.local.get(['examToken', 'attemptId'], (result) => {
    document.getElementById('token').textContent = result.examToken || 'Not available';
    document.getElementById('attemptId').textContent = result.attemptId || 'Not available';
  });

  document.getElementById('copyToken').addEventListener('click', () => {
    const token = document.getElementById('token').textContent;
    navigator.clipboard.writeText(token).then(() => {
      alert('Token copied!');
    });
  });
});